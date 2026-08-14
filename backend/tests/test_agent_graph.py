from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END

from app.config.settings import settings
from app.services.agent_graph import (
    build_agent_graph,
    create_llm,
    should_continue,
    _generate_title_if_empty,
    route_after_verify,
    MAX_VERIFY_RETRIES,
    Verdict,
    _decide_verification,
    _run_verdict,
)
from app.services.prompts import SYSTEM_PROMPT, VERIFY_PROMPT, build_rewrite_prompt


@pytest.fixture
def mock_conv_repo():
    """Mock ConversationRepo"""
    return MagicMock()


def test_build_agent_graph_registers_nodes(mock_conv_repo):
    """测试图注册了 generate_title / agent / tools 三个节点"""
    graph = build_agent_graph(mock_conv_repo)
    nodes = list(graph.get_graph().nodes)
    assert "generate_title" in nodes
    assert "agent" in nodes
    assert "tools" in nodes


def test_should_continue_without_tool_calls():
    """测试最后消息无工具调用时路由到 verifier"""
    state = {"messages": [AIMessage(content="你好")]}
    assert should_continue(state) == "verifier"


def test_should_continue_with_tool_calls():
    """测试最后消息含工具调用时路由到 tools"""
    msg = AIMessage(content="", tool_calls=[{"name": "calculator", "args": {}, "id": "1"}])
    state = {"messages": [msg]}
    assert should_continue(state) == "tools"


@pytest.mark.asyncio
async def test_generate_title_if_empty():
    """测试标题为空时调用 LLM 生成标题"""
    mock_llm = AsyncMock()
    mock_llm.ainvoke.return_value = MagicMock(content='"测试标题"')
    conv = MagicMock()
    conv.title = ""
    result = await _generate_title_if_empty(conv, [], mock_llm)
    assert result == "测试标题"


@pytest.mark.asyncio
async def test_generate_title_skipped_when_exists():
    """测试标题非空时跳过生成"""
    mock_llm = AsyncMock()
    conv = MagicMock()
    conv.title = "已有标题"
    result = await _generate_title_if_empty(conv, [], mock_llm)
    assert result is None
    mock_llm.ainvoke.assert_not_called()


@pytest.mark.asyncio
async def test_astream_runs_full_graph_with_title_and_tokens():
    """集成测试：真实跑完整图，验证标题写入数据库 + token 流式产出"""
    # 标题为空的对话，应触发 generate_title 节点生成标题
    conv = MagicMock()
    conv.title = ""
    conv_repo = MagicMock()
    conv_repo.get_by_id = AsyncMock(return_value=conv)
    conv_repo.update_title = AsyncMock(return_value=None)

    # 标题节点和 agent 节点各用一个 fake LLM（通过 streaming 参数区分）
    title_llm = GenericFakeChatModel(messages=iter([AIMessage(content='"测试标题"')]))
    agent_llm = GenericFakeChatModel(messages=iter([AIMessage(content="你好，世界")]))

    # 记录图内节点创建 LLM 时传入的 model 选择名，用于验证透传
    received_models = []

    def fake_create_llm(streaming: bool = True, model: str = "", enable_thinking: bool = True, max_tokens: int | None = None):
        received_models.append(model)
        return title_llm if not streaming else agent_llm

    graph = build_agent_graph(conv_repo)
    full_text = ""
    # verifier 节点真实调用 _run_verdict 需要结构化输出，fake LLM 不支持，
    # 这里 patch 成直接返回"准确"的 Verdict，让验证链路走 pass 正常结束
    async def fake_run_verdict(llm, messages):
        return Verdict(is_accurate=True, issues="")

    with patch("app.services.agent_graph._run_verdict", side_effect=fake_run_verdict):
        with patch("app.services.agent_graph.create_llm", side_effect=fake_create_llm):
            async for item in graph.astream(
                {
                    "messages": [HumanMessage(content="hi")],
                    "conv_id": "c1",
                    "user_id": "user-abc",  # 图节点按用户隔离查询，必须注入归属用户
                    "model": settings.MODEL_DASHSCOPE_QWEN,
                },
                stream_mode="messages",
            ):
                if isinstance(item, tuple):
                    chunk, _meta = item
                    if isinstance(chunk.content, str):
                        full_text += chunk.content

    # 标题已通过 generate_title 节点写入数据库
    conv_repo.update_title.assert_awaited_once_with("c1", "测试标题")
    # generate_title 节点必须按用户隔离查询对话（get_by_id 双参数防越权）
    conv_repo.get_by_id.assert_awaited_once_with("c1", "user-abc")
    # agent 节点的回复以 token 形式流式拼出（messages 流还包含标题 token，不影响）
    assert "你好，世界" in full_text
    # 图内节点应按所选模型创建 LLM（标题节点 + agent 节点 + verifier 节点各调用一次）。
    # 注意：三节点并行 fan-out，谁先调用 create_llm 顺序不固定，只校验次数与取值
    assert len(received_models) == 3
    assert all(m == settings.MODEL_DASHSCOPE_QWEN for m in received_models)


@pytest.mark.asyncio
async def test_title_failure_does_not_block_chat():
    """标题 LLM 抛异常时不应阻断聊天：agent 节点仍应正常产出回复"""
    conv = MagicMock()
    conv.title = ""
    conv_repo = MagicMock()
    conv_repo.get_by_id = AsyncMock(return_value=conv)
    conv_repo.update_title = AsyncMock(return_value=None)

    # 标题 LLM 模拟 Ollama 故障（抛连接错误）
    title_llm = MagicMock()

    async def boom(*args, **kwargs):
        raise ConnectionError("Ollama down")

    title_llm.ainvoke = boom
    agent_llm = GenericFakeChatModel(messages=iter([AIMessage(content="仍正常回复")]))

    # 记录图内节点创建 LLM 时传入的 model 选择名，用于验证透传
    received_models = []

    def fake_create_llm(streaming: bool = True, model: str = "", enable_thinking: bool = True, max_tokens: int | None = None):
        received_models.append(model)
        return title_llm if not streaming else agent_llm

    graph = build_agent_graph(conv_repo)
    full_text = ""
    # verifier 节点真实调用 _run_verdict 需要结构化输出，fake LLM 不支持，patch 成直接返回准确
    async def fake_run_verdict(llm, messages):
        return Verdict(is_accurate=True, issues="")

    with patch("app.services.agent_graph._run_verdict", side_effect=fake_run_verdict):
        with patch("app.services.agent_graph.create_llm", side_effect=fake_create_llm):
            async for item in graph.astream(
                {
                    "messages": [HumanMessage(content="hi")],
                    "conv_id": "c1",
                    "user_id": "user-abc",
                    "model": settings.MODEL_DASHSCOPE_QWEN,
                },
                stream_mode="messages",
            ):
                if isinstance(item, tuple):
                    chunk, _meta = item
                    if isinstance(chunk.content, str):
                        full_text += chunk.content

    # 标题生成失败被静默吞掉，聊天回复不受影响
    assert "仍正常回复" in full_text
    # 图内节点应按所选模型创建 LLM（标题节点 + agent 节点 + verifier 节点各调用一次）。
    # 并行 fan-out 下调用顺序不固定，只校验次数与取值
    assert len(received_models) == 3
    assert all(m == settings.MODEL_DASHSCOPE_QWEN for m in received_models)


@pytest.mark.asyncio
async def test_generate_title_node_exposes_title_in_updates():
    """测试 generate_title 节点把新标题写回状态，可用 stream_mode='updates' 实时取到"""
    conv = MagicMock()
    conv.title = ""
    conv_repo = MagicMock()
    conv_repo.get_by_id = AsyncMock(return_value=conv)
    conv_repo.update_title = AsyncMock(return_value=None)

    title_llm = GenericFakeChatModel(messages=iter([AIMessage(content='"集成标题"')]))
    agent_llm = GenericFakeChatModel(messages=iter([AIMessage(content="回复内容")]))

    def fake_create_llm(streaming: bool = True, model: str = "", enable_thinking: bool = True, max_tokens: int | None = None):
        return title_llm if not streaming else agent_llm

    graph = build_agent_graph(conv_repo)
    updates = []
    # verifier 节点真实调用 _run_verdict 需要结构化输出，fake LLM 不支持，patch 成直接返回准确
    async def fake_run_verdict(llm, messages):
        return Verdict(is_accurate=True, issues="")

    with patch("app.services.agent_graph._run_verdict", side_effect=fake_run_verdict):
        with patch("app.services.agent_graph.create_llm", side_effect=fake_create_llm):
            async for mode, data in graph.astream(
                {"messages": [HumanMessage(content="hi")], "conv_id": "c1", "user_id": "user-abc", "model": settings.MODEL_OLLAMA},
                stream_mode=["messages", "updates"],
            ):
                if mode == "updates":
                    updates.append(data)

    # generate_title 节点产出的标题能通过 updates 模式被上层拿到（供 SSE 推送前端）
    assert any(
        u.get("generate_title", {}).get("generated_title") == "集成标题"
        for u in updates
    )
    # 标题仍按原逻辑写入数据库；查询对话按归属用户隔离
    conv_repo.update_title.assert_awaited_once_with("c1", "集成标题")
    conv_repo.get_by_id.assert_awaited_once_with("c1", "user-abc")


def test_create_llm_ollama_model():
    """测试 create_llm 按 ollama-qwen3.5 创建 Ollama 配置的 LLM"""
    with patch("app.services.agent_graph.ChatOpenAI") as mock_cls:
        create_llm(streaming=True, model=settings.MODEL_OLLAMA)
    mock_cls.assert_called_once()
    kwargs = mock_cls.call_args.kwargs
    assert kwargs["base_url"] == settings.OLLAMA_BASE_URL + "/v1"
    assert kwargs["model"] == settings.LLM_MODEL
    assert kwargs["api_key"] == "ollama"
    assert kwargs["streaming"] is True


def test_create_llm_dashscope_model():
    """测试 create_llm 按 qwen3.7-flash 创建 DashScope 配置的 LLM"""
    with patch("app.services.agent_graph.ChatOpenAI") as mock_cls:
        create_llm(streaming=False, model=settings.MODEL_DASHSCOPE_QWEN)
    mock_cls.assert_called_once()
    kwargs = mock_cls.call_args.kwargs
    assert kwargs["base_url"] == settings.DASHSCOPE_BASE_URL
    assert kwargs["model"] == settings.DASHSCOPE_MODEL
    assert kwargs["api_key"] == settings.DASHSCOPE_API_KEY
    assert kwargs["streaming"] is False


def test_create_llm_dashscope_disables_thinking_for_title():
    """测试标题场景：关闭思考模式并限制 max_tokens，让标题秒回不被思考拖慢"""
    with patch("app.services.agent_graph.ChatOpenAI") as mock_cls:
        create_llm(
            streaming=False,
            model=settings.MODEL_DASHSCOPE_QWEN,
            enable_thinking=False,
            max_tokens=100,
        )
    kwargs = mock_cls.call_args.kwargs
    assert kwargs["max_tokens"] == 100
    # DashScope 兼容模式通过 extra_body 关闭思考
    assert kwargs["extra_body"] == {"enable_thinking": False}


def test_create_llm_ollama_ignores_thinking_params():
    """测试 Ollama 分支不受思考参数影响：不传 extra_body / max_tokens"""
    with patch("app.services.agent_graph.ChatOpenAI") as mock_cls:
        create_llm(
            streaming=True,
            model=settings.MODEL_OLLAMA,
            enable_thinking=False,
            max_tokens=100,
        )
    kwargs = mock_cls.call_args.kwargs
    assert kwargs["base_url"] == settings.OLLAMA_BASE_URL + "/v1"
    assert kwargs["model"] == settings.LLM_MODEL
    assert "extra_body" not in kwargs
    assert "max_tokens" not in kwargs


def test_create_llm_unknown_model_raises():
    """测试非空未知选择名抛 ValueError，避免静默回退掩盖配置漂移"""
    with pytest.raises(ValueError):
        create_llm(model="qwen3.7-flsh")  # 拼错的选择名


@pytest.mark.asyncio
async def test_agent_node_thinking_switch():
    """测试 thinking 开关只传给 agent 节点；标题节点无论开关如何都固定关闭思考"""
    conv = MagicMock()
    conv.title = ""
    conv_repo = MagicMock()
    conv_repo.get_by_id = AsyncMock(return_value=conv)
    conv_repo.update_title = AsyncMock(return_value=None)

    title_llm = GenericFakeChatModel(messages=iter([AIMessage(content='"标题"')]))
    agent_llm = GenericFakeChatModel(messages=iter([AIMessage(content="回复")]))

    received = []

    def fake_create_llm(streaming=True, model="", enable_thinking=True, max_tokens=None):
        received.append({"streaming": streaming, "enable_thinking": enable_thinking})
        return title_llm if not streaming else agent_llm

    graph = build_agent_graph(conv_repo)
    # verifier 节点真实调用 _run_verdict 需要结构化输出，fake LLM 不支持，patch 成直接返回准确
    async def fake_run_verdict(llm, messages):
        return Verdict(is_accurate=True, issues="")

    with patch("app.services.agent_graph._run_verdict", side_effect=fake_run_verdict):
        with patch("app.services.agent_graph.create_llm", side_effect=fake_create_llm):
            async for _item in graph.astream(
                {
                    "messages": [HumanMessage(content="hi")],
                    "conv_id": "c1",
                    "user_id": "user-abc",
                    "model": settings.MODEL_DASHSCOPE_QWEN,
                    "thinking": True,  # 用户在前端开启了深度思考
                },
                stream_mode="messages",
            ):
                pass

    # 并行 fan-out 下调用顺序不固定，按 streaming 区分两个节点的调用
    title_calls = [r for r in received if not r["streaming"]]
    agent_calls = [r for r in received if r["streaming"]]
    # 标题节点 + verifier 节点均为非流式调用（都关闭思考），各记录一次
    assert len(title_calls) == 2
    assert all(r["enable_thinking"] is False for r in title_calls)
    # agent 节点：开启思考时 enable_thinking=True
    assert len(agent_calls) == 1
    assert agent_calls[0]["enable_thinking"] is True


@pytest.mark.asyncio
async def test_agent_node_thinking_defaults_off():
    """测试缺省（输入不含 thinking）时 agent 节点思考模式默认关闭"""
    conv = MagicMock()
    conv.title = "已有标题"
    conv_repo = MagicMock()
    conv_repo.get_by_id = AsyncMock(return_value=conv)

    agent_llm = GenericFakeChatModel(messages=iter([AIMessage(content="回复")]))

    received = []

    def fake_create_llm(streaming=True, model="", enable_thinking=True, max_tokens=None):
        received.append({"streaming": streaming, "enable_thinking": enable_thinking})
        return agent_llm

    graph = build_agent_graph(conv_repo)
    # verifier 节点真实调用 _run_verdict 需要结构化输出，fake LLM 不支持，patch 成直接返回准确
    async def fake_run_verdict(llm, messages):
        return Verdict(is_accurate=True, issues="")

    with patch("app.services.agent_graph._run_verdict", side_effect=fake_run_verdict):
        with patch("app.services.agent_graph.create_llm", side_effect=fake_create_llm):
            async for _item in graph.astream(
                {"messages": [HumanMessage(content="hi")], "conv_id": "c1", "user_id": "user-abc"},
                stream_mode="messages",
            ):
                pass

    agent_calls = [r for r in received if r["streaming"]]
    assert len(agent_calls) == 1
    assert agent_calls[0]["enable_thinking"] is False


def test_create_llm_default_falls_back_to_ollama():
    """测试未指定 model 时回退本地 Ollama（向后兼容）"""
    with patch("app.services.agent_graph.ChatOpenAI") as mock_cls:
        create_llm(streaming=True)
    mock_cls.assert_called_once()
    kwargs = mock_cls.call_args.kwargs
    assert kwargs["base_url"] == settings.OLLAMA_BASE_URL + "/v1"
    assert kwargs["model"] == settings.LLM_MODEL
    assert kwargs["api_key"] == "ollama"


@pytest.mark.asyncio
async def test_astream_defaults_to_ollama_without_model():
    """测试输入不含 model 时图内节点缺省回退本地 Ollama"""
    conv = MagicMock()
    conv.title = "已有标题"  # 标题已存在，仅验证缺省 model 透传
    conv_repo = MagicMock()
    conv_repo.get_by_id = AsyncMock(return_value=conv)

    agent_llm = GenericFakeChatModel(messages=iter([AIMessage(content="默认回复")]))

    received_models = []

    def fake_create_llm(streaming: bool = True, model: str = "", enable_thinking: bool = True, max_tokens: int | None = None):
        received_models.append(model)
        return agent_llm

    graph = build_agent_graph(conv_repo)
    # verifier 节点真实调用 _run_verdict 需要结构化输出，fake LLM 不支持，patch 成直接返回准确
    async def fake_run_verdict(llm, messages):
        return Verdict(is_accurate=True, issues="")

    with patch("app.services.agent_graph._run_verdict", side_effect=fake_run_verdict):
        with patch("app.services.agent_graph.create_llm", side_effect=fake_create_llm):
            async for _item in graph.astream(
                {"messages": [HumanMessage(content="hi")], "conv_id": "c1", "user_id": "user-abc"},
                stream_mode="messages",
            ):
                pass

    # 标题节点 + agent 节点 + verifier 节点各调用一次 create_llm，且均缺省回退 Ollama 选择名。
    # 并行 fan-out 下调用顺序不固定，只校验次数与取值
    assert len(received_models) == 3
    assert all(m == settings.MODEL_OLLAMA for m in received_models)


def test_should_continue_without_tool_calls_routes_to_verifier():
    """最后消息无工具调用时路由到 verifier（不再直接 END）"""
    state = {"messages": [AIMessage(content="你好")]}
    assert should_continue(state) == "verifier"


def test_route_after_verify_with_feedback():
    """有验证反馈（需重写）时回 agent"""
    assert route_after_verify({"verification_feedback": "金额错误"}) == "agent"


def test_route_after_verify_without_feedback():
    """无反馈（通过或超限）时走 END"""
    assert route_after_verify({"verification_feedback": ""}) == END


def test_max_verify_retries_is_two():
    """重试上限固定为 2 次"""
    assert MAX_VERIFY_RETRIES == 2


def test_decide_verification_accurate_passes():
    """准确：反馈清空，result=pass，计数不变"""
    state = {"rewrite_count": 0}
    out = _decide_verification(Verdict(is_accurate=True, issues=""), state)
    assert out["verification_result"] == "pass"
    assert out["verification_feedback"] == ""
    assert out["rewrite_count"] == 0


def test_decide_verification_retry_increments_count():
    """不准确且未超限：写入反馈，计数+1，result=retry"""
    state = {"rewrite_count": 0}
    out = _decide_verification(Verdict(is_accurate=False, issues="金额错误"), state)
    assert out["verification_result"] == "retry"
    assert out["verification_feedback"] == "金额错误"
    assert out["rewrite_count"] == 1


def test_decide_verification_fail_when_over_limit():
    """不准确且已达上限：清空反馈，result=fail，计数不变"""
    state = {"rewrite_count": MAX_VERIFY_RETRIES}
    out = _decide_verification(Verdict(is_accurate=False, issues="还是错"), state)
    assert out["verification_result"] == "fail"
    assert out["verification_feedback"] == ""
    assert out["rewrite_count"] == MAX_VERIFY_RETRIES


@pytest.mark.asyncio
async def test_run_verdict_injects_verify_prompt_and_calls_structured_llm():
    """_run_verdict 注入验证提示词并调用结构化输出"""
    mock_llm = MagicMock()
    structured = MagicMock()
    structured.ainvoke = AsyncMock(return_value=Verdict(is_accurate=True, issues=""))
    mock_llm.with_structured_output.return_value = structured

    messages = [HumanMessage(content="hi")]
    result = await _run_verdict(mock_llm, messages)

    assert result.is_accurate is True
    # 验证提示词作为 SystemMessage 前置注入
    call_messages = structured.ainvoke.call_args.args[0]
    assert call_messages[0].type == "system"
    assert VERIFY_PROMPT in call_messages[0].content
    # 原始对话消息保持在提示词之后
    assert call_messages[1] == messages[0]


@pytest.mark.asyncio
async def test_run_verdict_filters_system_role_message():
    """_run_verdict 必须过滤掉角色设定 SystemMessage（如 SYSTEM_PROMPT"你是小励"），
    只保留 user/assistant/tool 对话消息交给质检员；否则两条 SystemMessage 连排
    会让模型把角色设定当成对话参与者，导致校验对象搞错（用户实测 bug）"""
    mock_llm = MagicMock()
    structured = MagicMock()
    structured.ainvoke = AsyncMock(return_value=Verdict(is_accurate=True, issues=""))
    mock_llm.with_structured_output.return_value = structured

    # 模拟真实场景：state["messages"] 开头有 chat_service 注入的 SYSTEM_PROMPT
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content="现在几点了？"),
        AIMessage(content="候选回复"),
    ]
    result = await _run_verdict(mock_llm, messages)

    assert result.is_accurate is True
    call_messages = structured.ainvoke.call_args.args[0]
    # 除 VERIFY_PROMPT 外不再有第二条 SystemMessage（角色设定被过滤）
    system_msgs = [m for m in call_messages if isinstance(m, SystemMessage)]
    assert len(system_msgs) == 1
    assert system_msgs[0].content == VERIFY_PROMPT
    # 对话消息完整保留且顺序不变
    assert [type(m) for m in call_messages[1:]] == [HumanMessage, AIMessage]


@pytest.mark.asyncio
async def test_run_verdict_filters_stale_rounds_keeps_candidate_and_tool():
    """_run_verdict 必须丢弃历史中已判错/重写的旧回复与带工具调用的中间轮，
    只保留：用户消息 + 工具结果 + 最后一条无工具调用的候选回复。
    否则质检员会看到互相矛盾的多轮回复（如首轮幻觉 320 元、重写轮 70 元），
    被历史干扰而误判正确回复不准确（用户实测 bug）"""
    mock_llm = MagicMock()
    structured = MagicMock()
    structured.ainvoke = AsyncMock(return_value=Verdict(is_accurate=True, issues=""))
    mock_llm.with_structured_output.return_value = structured

    # 模拟真实重写场景的消息序列（含首轮幻觉 + 工具调用中间轮 + 工具结果 + 重写候选）
    messages = [
        HumanMessage(content="我这个月一共花了 800 块，是不是？"),
        # 首轮幻觉回复（320 元，错）
        AIMessage(content="我这个月一共花了 320 元"),
        # 重写轮中间轮：先声明再调用工具（带 tool_calls 的 assistant）
        AIMessage(
            content="让我重新核对一下",
            tool_calls=[{"name": "list_expenses", "args": {"page": 1, "page_size": 100}, "id": "1", "type": "tool_call"}],
        ),
        # 工具结果
        ToolMessage(content='{"total": 6, "items": [...]}', name="list_expenses", tool_call_id="1"),
        # 重写轮最终候选（70 元，正确）
        AIMessage(content="我这个月一共花了 70 元"),
    ]
    await _run_verdict(mock_llm, messages)

    call_messages = structured.ainvoke.call_args.args[0]
    # 前置 VERIFY_PROMPT 后，其余消息应只剩：用户 + 工具结果 + 候选回复
    remaining = call_messages[1:]
    # 丢弃了首轮幻觉回复与带工具调用的中间轮
    assert [type(m) for m in remaining] == [HumanMessage, ToolMessage, AIMessage]
    # 候选回复必须是最后一条无工具调用的 assistant（70 元那条）
    assert remaining[-1].content == "我这个月一共花了 70 元"
    assert not any("320 元" in m.content for m in remaining if isinstance(m, AIMessage))


def test_agent_state_declares_verification_result():
    """verification_result 必须在状态 schema 中声明，否则 LangGraph 会静默丢弃该键"""
    graph = build_agent_graph(MagicMock())
    # 编译后的图把状态 schema 展开为 channels：声明过的键才会生成对应通道，
    # 未声明的键会被 LangGraph 静默丢弃，channels 中查不到
    assert "verification_result" in graph.builder.channels


@pytest.mark.asyncio
async def test_build_graph_registers_verifier_node(mock_conv_repo):
    """图注册了 generate_title / agent / tools / verifier 四个节点"""
    graph = build_agent_graph(mock_conv_repo)
    nodes = list(graph.get_graph().nodes)
    assert "verifier" in nodes
    assert "agent" in nodes
    assert "tools" in nodes


@pytest.mark.asyncio
async def test_verifier_accurate_ends_graph():
    """验证通过：verification_result=pass，图正常结束"""
    conv = MagicMock()
    conv.title = "已有标题"  # 跳过标题生成，聚焦验证链路
    conv_repo = MagicMock()
    conv_repo.get_by_id = AsyncMock(return_value=conv)
    conv_repo.update_title = AsyncMock(return_value=None)

    agent_llm = GenericFakeChatModel(messages=iter([AIMessage(content="回复")]))

    # verifier 的 LLM 调用被替换为直接返回 Verdict（避免真实结构化输出依赖）
    async def fake_run_verdict(llm, messages):
        return Verdict(is_accurate=True, issues="")

    graph = build_agent_graph(conv_repo)
    updates = []
    with (
        patch("app.services.agent_graph._run_verdict", side_effect=fake_run_verdict),
        patch("app.services.agent_graph.create_llm", side_effect=lambda streaming=True, model="", enable_thinking=True, max_tokens=None: agent_llm),
    ):
        async for mode, data in graph.astream(
            {"messages": [HumanMessage(content="hi")], "conv_id": "c1", "user_id": "user-abc", "model": settings.MODEL_OLLAMA},
            stream_mode=["messages", "updates"],
        ):
            if mode == "updates":
                updates.append(data)

    assert any(u.get("verifier", {}).get("verification_result") == "pass" for u in updates)


@pytest.mark.asyncio
async def test_verifier_degrades_to_pass_when_llm_fails():
    """验证器 LLM 调用失败时降级为通过，图正常结束不崩溃"""
    conv = MagicMock()
    conv.title = "已有标题"
    conv_repo = MagicMock()
    conv_repo.get_by_id = AsyncMock(return_value=conv)
    conv_repo.update_title = AsyncMock(return_value=None)

    agent_llm = GenericFakeChatModel(messages=iter([AIMessage(content="回复")]))

    # 验证器调用抛异常（模拟网络故障）
    async def boom_verdict(llm, messages):
        raise ConnectionError("Ollama down")

    graph = build_agent_graph(conv_repo)
    updates = []
    with (
        patch("app.services.agent_graph._run_verdict", side_effect=boom_verdict),
        patch("app.services.agent_graph.create_llm", side_effect=lambda streaming=True, model="", enable_thinking=True, max_tokens=None: agent_llm),
    ):
        async for mode, data in graph.astream(
            {"messages": [HumanMessage(content="hi")], "conv_id": "c1", "user_id": "user-abc", "model": settings.MODEL_OLLAMA},
            stream_mode=["messages", "updates"],
        ):
            if mode == "updates":
                updates.append(data)

    # 降级为 pass：图正常结束，未崩溃
    assert any(u.get("verifier", {}).get("verification_result") == "pass" for u in updates)


@pytest.mark.asyncio
async def test_verifier_retry_then_pass_loops_through_agent():
    """首次不准确回 agent 重写，重写后准确走 pass"""
    conv = MagicMock()
    conv.title = "已有标题"
    conv_repo = MagicMock()
    conv_repo.get_by_id = AsyncMock(return_value=conv)
    conv_repo.update_title = AsyncMock(return_value=None)

    # 首轮与重写轮各用一条 fake 回复
    first_llm = GenericFakeChatModel(messages=iter([AIMessage(content="首次回复")]))
    rewrite_llm = GenericFakeChatModel(messages=iter([AIMessage(content="重写回复")]))

    # 按 streaming 区分：首轮流式(True)拿 first_llm，重写轮非流式(False)拿 rewrite_llm
    def fake_create_llm(streaming=True, model="", enable_thinking=True, max_tokens=None):
        return first_llm if streaming else rewrite_llm

    # 第一次验证判不准，第二次判准确
    calls = {"n": 0}

    async def fake_run_verdict(llm, messages):
        calls["n"] += 1
        if calls["n"] == 1:
            return Verdict(is_accurate=False, issues="金额错误")
        return Verdict(is_accurate=True, issues="")

    graph = build_agent_graph(conv_repo)
    updates = []
    with (
        patch("app.services.agent_graph._run_verdict", side_effect=fake_run_verdict),
        patch("app.services.agent_graph.create_llm", side_effect=fake_create_llm),
    ):
        async for mode, data in graph.astream(
            {"messages": [HumanMessage(content="hi")], "conv_id": "c1", "user_id": "user-abc", "model": settings.MODEL_OLLAMA},
            stream_mode=["messages", "updates"],
        ):
            if mode == "updates":
                updates.append(data)

    results = [u["verifier"]["verification_result"] for u in updates if "verifier" in u]
    assert results == ["retry", "pass"]
    # 重写轮非流式 LLM 产出的"重写回复"应出现在 agent 消息流中
    assert any(
        "重写回复" in m.content
        for u in updates
        for m in u.get("agent", {}).get("messages", [])
    )


@pytest.mark.asyncio
async def test_verifier_fail_when_retries_exhausted():
    """超过重试上限：verification_result=fail，不再循环"""
    conv = MagicMock()
    conv.title = "已有标题"
    conv_repo = MagicMock()
    conv_repo.get_by_id = AsyncMock(return_value=conv)
    conv_repo.update_title = AsyncMock(return_value=None)

    first_llm = GenericFakeChatModel(messages=iter([AIMessage(content="首次")]))
    rewrite_llm = GenericFakeChatModel(messages=iter([AIMessage(content="重写1"), AIMessage(content="重写2")]))

    def fake_create_llm(streaming=True, model="", enable_thinking=True, max_tokens=None):
        return first_llm if streaming else rewrite_llm

    # 每次都判不准
    async def fake_run_verdict(llm, messages):
        return Verdict(is_accurate=False, issues="始终不准")

    graph = build_agent_graph(conv_repo)
    updates = []
    with (
        patch("app.services.agent_graph._run_verdict", side_effect=fake_run_verdict),
        patch("app.services.agent_graph.create_llm", side_effect=fake_create_llm),
    ):
        async for mode, data in graph.astream(
            {"messages": [HumanMessage(content="hi")], "conv_id": "c1", "user_id": "user-abc", "model": settings.MODEL_OLLAMA},
            stream_mode=["messages", "updates"],
        ):
            if mode == "updates":
                updates.append(data)

    results = [u["verifier"]["verification_result"] for u in updates if "verifier" in u]
    # 首次 + 重写1 + 重写2 共三次验证，前两次 retry 最后一次 fail
    assert results == ["retry", "retry", "fail"]
