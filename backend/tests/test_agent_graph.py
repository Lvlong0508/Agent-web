from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage
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
from app.services.prompts import VERIFY_PROMPT


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
    # 图内节点应按所选模型创建 LLM（标题节点 + agent 节点各调用一次）。
    # 注意：两节点是并行 fan-out，谁先调用 create_llm 顺序不固定，只校验次数与取值
    assert len(received_models) == 2
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
    # 图内节点应按所选模型创建 LLM（标题节点 + agent 节点各调用一次）。
    # 并行 fan-out 下调用顺序不固定，只校验次数与取值
    assert len(received_models) == 2
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
    # 标题节点：无论 thinking 开关如何，都关闭思考（保证标题秒回、先于内容）
    assert len(title_calls) == 1
    assert title_calls[0]["enable_thinking"] is False
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
    with patch("app.services.agent_graph.create_llm", side_effect=fake_create_llm):
        async for _item in graph.astream(
            {"messages": [HumanMessage(content="hi")], "conv_id": "c1", "user_id": "user-abc"},
            stream_mode="messages",
        ):
            pass

    # 标题节点 + agent 节点各调用一次 create_llm，且均缺省回退 Ollama 选择名。
    # 并行 fan-out 下调用顺序不固定，只校验次数与取值
    assert len(received_models) == 2
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
