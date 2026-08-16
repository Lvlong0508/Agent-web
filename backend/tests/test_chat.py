import pytest
from unittest.mock import AsyncMock, MagicMock
from langchain_core.messages import AIMessage as RealAIMessage
from langchain_core.messages import SystemMessage
from pydantic import ValidationError

from app.auth import current_user_id
from app.config.settings import settings
from app.models.conversation import Conversation
from app.schemas.chat import SendMessageRequest
from app.services.chat_service import USER_FRIENDLY_ERROR, ChatService
from app.services.agent.prompts import REPLY_ON_VERIFY_FAILED, SYSTEM_PROMPT, build_system_prompt


@pytest.fixture
def mock_db():
    """Mock MongoDB 数据库实例"""
    return MagicMock()


@pytest.fixture(autouse=True)
def user_context():
    """模拟 get_current_user_id 依赖：为每个用例注入固定用户身份并复位"""
    token = current_user_id.set("anonymous")
    yield
    current_user_id.reset(token)


@pytest.fixture
def chat_service(mock_db):
    """返回注入 mock db 的 ChatService"""
    service = ChatService(mock_db)
    # 全链路落库在旧测试中不关心，统一 mock 掉 create，避免调用真实集合
    service.agent_run_repo = MagicMock()
    service.agent_run_repo.create = AsyncMock(return_value=None)
    return service


@pytest.mark.asyncio
async def test_create_conversation(chat_service):
    """测试创建对话返回正确的格式"""
    # 模拟 ConversationRepo.create 返回一个 Conversation 对象
    chat_service.conv_repo.create = AsyncMock(return_value=Conversation(
        _id="test-id", user_id="user-1", title="",
    ))

    result = await chat_service.create_conversation()

    assert result["id"] == "test-id"
    assert result["title"] == ""
    assert "created_at" in result


@pytest.mark.asyncio
async def test_list_conversations_empty_title(chat_service):
    """测试空标题对话在列表中显示为'新对话'"""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    mock_convs = [
        Conversation(_id="c1", user_id="u1", title="对话1", created_at=now, updated_at=now),
        Conversation(_id="c2", user_id="u1", title="", created_at=now, updated_at=now),
    ]
    chat_service.conv_repo.list_by_user = AsyncMock(return_value=mock_convs)

    result = await chat_service.list_conversations()

    assert len(result) == 2
    assert result[0]["title"] == "对话1"
    assert result[1]["title"] == "新对话"


@pytest.mark.asyncio
async def test_get_messages_unauthorized(chat_service):
    """repo 按 user_id 过滤查不到（越权）时抛 PermissionError"""
    chat_service.conv_repo.get_by_id = AsyncMock(return_value=None)

    with pytest.raises(PermissionError):
        await chat_service.get_messages("c1")


@pytest.mark.asyncio
async def test_delete_conversation_unauthorized(chat_service):
    """repo 按 user_id 过滤查不到（越权）时抛 PermissionError"""
    chat_service.conv_repo.get_by_id = AsyncMock(return_value=None)

    with pytest.raises(PermissionError):
        await chat_service.delete_conversation("c1")


@pytest.mark.asyncio
async def test_chat_stream_respects_current_user(chat_service):
    """归属校验基于 contextvar 当前用户而非硬编码 anonymous"""
    token = current_user_id.set("other-user")
    try:
        conv = Conversation(_id="c1", user_id="other-user")
        chat_service.conv_repo.get_by_id = AsyncMock(return_value=conv)
        chat_service.msg_repo.list_by_conversation = AsyncMock(return_value=[])
        chat_service.msg_repo.create = AsyncMock(return_value=None)

        mock_chunk = MagicMock()
        mock_chunk.content = "你好"
        mock_meta = {"langgraph_node": "agent"}

        async def fake_astream(input, **kwargs):
            yield ("messages", (mock_chunk, mock_meta))
            # 验证通过：推送最终版（token 缓冲后经 final 事件一次性给出）
            yield ("custom", {"type": "verifier.verdict", "capability": "verifier",
                              "status": "completed", "payload": {"result": "pass"}})

        chat_service.graph = MagicMock()
        chat_service.graph.astream = fake_astream

        tokens = []
        async for chunk in chat_service.chat_stream(
            "c1", "hello", settings.MODEL_DASHSCOPE_QWEN
        ):
            tokens.append(chunk)
        assert any('"final": "你好"' in t for t in tokens)
    finally:
        current_user_id.reset(token)


@pytest.mark.asyncio
async def test_chat_stream_saves_messages(chat_service):
    """测试聊天流通过 agent 图产出 token 并保存 user/assistant 消息"""
    conv = Conversation(_id="c1", user_id="anonymous")
    chat_service.conv_repo.get_by_id = AsyncMock(return_value=conv)
    chat_service.msg_repo.list_by_conversation = AsyncMock(return_value=[])
    chat_service.msg_repo.create = AsyncMock(return_value=None)

    # Mock agent 图：用异步生成器模拟 astream 逐块产出 token
    mock_chunk = MagicMock()
    mock_chunk.content = "你好"
    # metadata 必须标记 langgraph_node="agent"，否则会被 chat_stream 当成
    # generate_title 节点的标题输出过滤掉
    mock_meta = {"langgraph_node": "agent"}

    graph_input = {}

    async def fake_astream(input, **kwargs):
        """假的 graph.astream：记录输入并产出 (模式, 数据) 元组"""
        graph_input.update(input)
        # 业务事件走 custom 流（verifier 判定），messages 流只出 token：
        # chat_service 订阅 custom 事件驱动 final 推送
        yield ("messages", (mock_chunk, mock_meta))
        yield ("custom", {"type": "verifier.verdict", "capability": "verifier",
                          "status": "completed", "payload": {"result": "pass"}})

    chat_service.graph = MagicMock()
    chat_service.graph.astream = fake_astream

    tokens = []
    async for chunk in chat_service.chat_stream("c1", "hello", settings.MODEL_DASHSCOPE_QWEN):
        tokens.append(chunk)

    # 验证通过后经 final 事件收到完整回复，以及结束标志 [DONE]
    assert any('"final": "你好"' in t for t in tokens)
    assert any("[DONE]" in t for t in tokens)
    # user 和 assistant 消息各保存一次
    assert chat_service.msg_repo.create.call_count == 2
    # model 透传到 agent 图的输入
    assert graph_input["model"] == settings.MODEL_DASHSCOPE_QWEN


@pytest.mark.asyncio
async def test_chat_stream_prepends_system_prompt(chat_service):
    """测试系统提示词在入口状态最前面注入一次（小励角色设定）"""
    from app.models.message import Message

    conv = Conversation(_id="c1", user_id="anonymous")
    chat_service.conv_repo.get_by_id = AsyncMock(return_value=conv)
    # 历史消息包含刚保存的用户消息（真实流程：save 后 list 会带回）
    chat_service.msg_repo.list_by_conversation = AsyncMock(return_value=[
        Message(conversation_id="c1", role="user", content="hello"),
    ])
    chat_service.msg_repo.create = AsyncMock(return_value=None)

    mock_chunk = MagicMock()
    mock_chunk.content = "回复"
    mock_meta = {"langgraph_node": "agent"}
    graph_input = {}

    async def fake_astream(input, **kwargs):
        """假的 graph.astream：记录输入并产出 (模式, 数据) 元组"""
        graph_input.update(input)
        yield ("messages", (mock_chunk, mock_meta))

    chat_service.graph = MagicMock()
    chat_service.graph.astream = fake_astream

    tokens = []
    async for chunk in chat_service.chat_stream("c1", "hello", settings.MODEL_OLLAMA):
        tokens.append(chunk)

    # 注入到图的消息流：第一条是系统提示词，随后才是用户消息
    messages = graph_input["messages"]
    assert isinstance(messages[0], SystemMessage)
    # 系统提示词 = 基础提示词 + 当前日期注入（agent 知道今天是哪年）
    import time
    today = time.strftime("%Y-%m-%d", time.localtime())
    assert messages[0].content == build_system_prompt(today)
    assert messages[1].content == "hello"


@pytest.mark.asyncio
async def test_chat_stream_pushes_generated_title(chat_service):
    """测试标题节点生成的标题会以 SSE 事件推给前端"""
    conv = Conversation(_id="c1", user_id="anonymous")
    chat_service.conv_repo.get_by_id = AsyncMock(return_value=conv)
    chat_service.msg_repo.list_by_conversation = AsyncMock(return_value=[])
    chat_service.msg_repo.create = AsyncMock(return_value=None)

    # 模拟图依次产出：标题节点的增量状态（含新标题）+ 一条 agent token
    mock_chunk = MagicMock()
    mock_chunk.content = "你好"
    mock_meta = {"langgraph_node": "agent"}

    async def fake_astream(input, **kwargs):
        """假的 graph.astream：先发标题事件，再发 agent token + 验证通过"""
        yield ("custom", {"type": "title.completed", "capability": "title",
                          "status": "completed", "payload": {"title": "新标题"}})
        yield ("messages", (mock_chunk, mock_meta))
        yield ("custom", {"type": "verifier.verdict", "capability": "verifier",
                          "status": "completed", "payload": {"result": "pass"}})

    chat_service.graph = MagicMock()
    chat_service.graph.astream = fake_astream

    tokens = []
    async for chunk in chat_service.chat_stream("c1", "hello", settings.MODEL_DASHSCOPE_QWEN):
        tokens.append(chunk)

    # 标题事件与最终版回复都应推送
    assert any('"title": "新标题"' in t for t in tokens)
    assert any('"final": "你好"' in t for t in tokens)


@pytest.mark.asyncio
async def test_chat_stream_ignores_empty_title_update(chat_service):
    """测试标题节点未生成标题（空串）时不应推送标题事件"""
    conv = Conversation(_id="c1", user_id="anonymous")
    chat_service.conv_repo.get_by_id = AsyncMock(return_value=conv)
    chat_service.msg_repo.list_by_conversation = AsyncMock(return_value=[])
    chat_service.msg_repo.create = AsyncMock(return_value=None)

    mock_chunk = MagicMock()
    mock_chunk.content = "你好"
    mock_meta = {"langgraph_node": "agent"}

    async def fake_astream(input, **kwargs):
        """假的 graph.astream：标题事件为空串，仅产出一条 token + 验证通过"""
        yield ("custom", {"type": "title.completed", "capability": "title",
                          "status": "completed", "payload": {"title": ""}})
        yield ("messages", (mock_chunk, mock_meta))
        yield ("custom", {"type": "verifier.verdict", "capability": "verifier",
                          "status": "completed", "payload": {"result": "pass"}})

    chat_service.graph = MagicMock()
    chat_service.graph.astream = fake_astream

    tokens = []
    async for chunk in chat_service.chat_stream("c1", "hello", settings.MODEL_DASHSCOPE_QWEN):
        tokens.append(chunk)

    # 不应出现标题事件，最终版经 final 事件给出
    assert not any('"title"' in t for t in tokens)
    assert any('"final": "你好"' in t for t in tokens)


@pytest.mark.asyncio
async def test_chat_stream_filters_title_token(chat_service):
    """测试 generate_title 节点的标题输出不会当成回复 token 拼进气泡"""
    conv = Conversation(_id="c1", user_id="anonymous")
    chat_service.conv_repo.get_by_id = AsyncMock(return_value=conv)
    chat_service.msg_repo.list_by_conversation = AsyncMock(return_value=[])
    chat_service.msg_repo.create = AsyncMock(return_value=None)

    # 标题节点的 LLM 输出也会出现在 messages 流（非流式调用也会弹出一个完整
    # chunk），metadata 标记为 generate_title，必须被过滤
    title_chunk = MagicMock()
    title_chunk.content = "新标题"
    agent_chunk = MagicMock()
    agent_chunk.content = "回复内容"

    async def fake_astream(input, **kwargs):
        """假的 graph.astream：先弹标题 chunk，再弹真正的回复 token + 验证通过"""
        yield ("messages", (title_chunk, {"langgraph_node": "generate_title"}))
        yield ("messages", (agent_chunk, {"langgraph_node": "agent"}))
        yield ("custom", {"type": "verifier.verdict", "capability": "verifier",
                          "status": "completed", "payload": {"result": "pass"}})

    chat_service.graph = MagicMock()
    chat_service.graph.astream = fake_astream

    tokens = []
    async for chunk in chat_service.chat_stream("c1", "hello", settings.MODEL_DASHSCOPE_QWEN):
        tokens.append(chunk)

    # 最终版只应含 agent 节点的回复，标题 token 不得混入
    assert any('"final": "回复内容"' in t for t in tokens)
    assert not any("新标题" in t for t in tokens)


@pytest.mark.asyncio
async def test_chat_stream_passes_thinking(chat_service):
    """测试思考开关透传到 agent 图的输入"""
    conv = Conversation(_id="c1", user_id="anonymous")
    chat_service.conv_repo.get_by_id = AsyncMock(return_value=conv)
    chat_service.msg_repo.list_by_conversation = AsyncMock(return_value=[])
    chat_service.msg_repo.create = AsyncMock(return_value=None)

    mock_chunk = MagicMock()
    mock_chunk.content = "你好"
    mock_meta = {"langgraph_node": "agent"}
    graph_input = {}

    async def fake_astream(input, **kwargs):
        """假的 graph.astream：记录输入并产出一条 token"""
        graph_input.update(input)
        yield ("messages", (mock_chunk, mock_meta))

    chat_service.graph = MagicMock()
    chat_service.graph.astream = fake_astream

    async for _ in chat_service.chat_stream("c1", "hello", settings.MODEL_DASHSCOPE_QWEN, True):
        pass

    # 思考开关已透传给图（true），由 agent 节点据此决定是否开启思考模式
    assert graph_input["thinking"] is True


def test_send_message_request_thinking_defaults_false():
    """测试请求体 thinking 默认关闭，且可显式开启"""
    req = SendMessageRequest(content="hi", model=settings.MODEL_DASHSCOPE_QWEN)
    assert req.thinking is False
    req_on = SendMessageRequest(
        content="hi", model=settings.MODEL_DASHSCOPE_QWEN, thinking=True
    )
    assert req_on.thinking is True


def test_send_message_request_rejects_unknown_model():
    """测试未知模型选择名在请求校验阶段被拒绝"""
    with pytest.raises(ValidationError):
        SendMessageRequest(content="hi", model="unknown-model")


@pytest.mark.asyncio
async def test_chat_stream_pushes_rewriting_event(chat_service):
    """verifier 判不准确时推送 rewriting 事件，重写轮 token 不推前端"""
    conv = Conversation(_id="c1", user_id="anonymous")
    chat_service.conv_repo.get_by_id = AsyncMock(return_value=conv)
    chat_service.msg_repo.list_by_conversation = AsyncMock(return_value=[])
    chat_service.msg_repo.create = AsyncMock(return_value=None)

    first_chunk = MagicMock()
    first_chunk.content = "首次回复"
    first_chunk.tool_call_chunks = []
    rewrite_chunk = MagicMock()
    rewrite_chunk.content = "重写回复"
    rewrite_chunk.tool_call_chunks = []

    async def fake_astream(input, **kwargs):
        """首轮流式 token → verifier retry → 重写轮 token → verifier pass"""
        yield ("messages", (first_chunk, {"langgraph_node": "agent"}))
        yield ("custom", {"type": "verifier.verdict", "capability": "verifier",
                          "status": "completed", "payload": {"result": "retry"}})
        yield ("messages", (rewrite_chunk, {"langgraph_node": "agent"}))
        yield ("custom", {"type": "verifier.verdict", "capability": "verifier",
                          "status": "completed", "payload": {"result": "pass"}})

    chat_service.graph = MagicMock()
    chat_service.graph.astream = fake_astream

    tokens = []
    async for chunk in chat_service.chat_stream("c1", "hello", settings.MODEL_DASHSCOPE_QWEN):
        tokens.append(chunk)

    # rewriting 事件已推送
    assert any('"rewriting"' in t for t in tokens)
    # 首轮的 token 不推前端（验证通过前缓冲）；重写轮内容经 final 事件推送
    assert not any('"token": "首次回复"' in t for t in tokens)
    assert any('"final": "重写回复"' in t for t in tokens)


@pytest.mark.asyncio
async def test_chat_stream_pushes_final_after_rewrite(chat_service):
    """重写后验证通过：推送 final 事件（最终版完整文本），assistant 保存最终版"""
    conv = Conversation(_id="c1", user_id="anonymous")
    chat_service.conv_repo.get_by_id = AsyncMock(return_value=conv)
    chat_service.msg_repo.list_by_conversation = AsyncMock(return_value=[])
    chat_service.msg_repo.create = AsyncMock(return_value=None)

    first_chunk = MagicMock()
    first_chunk.content = "首次回复"
    first_chunk.tool_call_chunks = []
    rewrite_chunk = MagicMock()
    rewrite_chunk.content = "最终版回复"
    rewrite_chunk.tool_call_chunks = []

    async def fake_astream(input, **kwargs):
        """首轮 token → retry → 重写轮 token → verifier pass"""
        yield ("messages", (first_chunk, {"langgraph_node": "agent"}))
        yield ("custom", {"type": "verifier.verdict", "capability": "verifier",
                          "status": "completed", "payload": {"result": "retry"}})
        yield ("messages", (rewrite_chunk, {"langgraph_node": "agent"}))
        yield ("custom", {"type": "verifier.verdict", "capability": "verifier",
                          "status": "completed", "payload": {"result": "pass"}})

    chat_service.graph = MagicMock()
    chat_service.graph.astream = fake_astream

    tokens = []
    async for chunk in chat_service.chat_stream("c1", "hello", settings.MODEL_DASHSCOPE_QWEN):
        tokens.append(chunk)

    # final 事件携带最终版完整文本
    assert any('"final": "最终版回复"' in t for t in tokens)
    # assistant 保存的是最终版（而非首轮残稿）
    calls = [c.args[0] for c in chat_service.msg_repo.create.call_args_list]
    assistant_saved = [m for m in calls if m.role == "assistant"][0]
    assert assistant_saved.content == "最终版回复"


@pytest.mark.asyncio
async def test_chat_stream_handles_rewrite_round_emitting_full_aimessage(chat_service):
    """重写轮非流式 LLM 产出完整 AIMessage（无 tool_call_chunks）时不应崩溃"""
    conv = Conversation(_id="c1", user_id="anonymous")
    chat_service.conv_repo.get_by_id = AsyncMock(return_value=conv)
    chat_service.msg_repo.list_by_conversation = AsyncMock(return_value=[])
    chat_service.msg_repo.create = AsyncMock(return_value=None)

    first_chunk = MagicMock()
    first_chunk.content = "首次回复"
    first_chunk.tool_call_chunks = []
    # 重写轮：真实非流式产出的是完整 AIMessage，没有 tool_call_chunks 属性
    rewrite_msg = RealAIMessage(content="最终版回复")

    async def fake_astream(input, **kwargs):
        """首轮 token → retry → 重写轮完整 AIMessage → verifier pass"""
        yield ("messages", (first_chunk, {"langgraph_node": "agent"}))
        yield ("custom", {"type": "verifier.verdict", "capability": "verifier",
                          "status": "completed", "payload": {"result": "retry"}})
        yield ("messages", (rewrite_msg, {"langgraph_node": "agent"}))
        yield ("custom", {"type": "verifier.verdict", "capability": "verifier",
                          "status": "completed", "payload": {"result": "pass"}})

    chat_service.graph = MagicMock()
    chat_service.graph.astream = fake_astream

    tokens = []
    async for chunk in chat_service.chat_stream("c1", "hello", settings.MODEL_DASHSCOPE_QWEN):
        tokens.append(chunk)

    # 不崩溃且最终版正确推送并落库
    assert any('"final": "最终版回复"' in t for t in tokens)
    calls = [c.args[0] for c in chat_service.msg_repo.create.call_args_list]
    assistant_saved = [m for m in calls if m.role == "assistant"][0]
    assert assistant_saved.content == "最终版回复"


@pytest.mark.asyncio
async def test_chat_stream_fail_returns_fixed_message(chat_service):
    """验证超限 fail：返回固定文案，assistant 保存该文案"""
    conv = Conversation(_id="c1", user_id="anonymous")
    chat_service.conv_repo.get_by_id = AsyncMock(return_value=conv)
    chat_service.msg_repo.list_by_conversation = AsyncMock(return_value=[])
    chat_service.msg_repo.create = AsyncMock(return_value=None)

    async def fake_astream(input, **kwargs):
        yield ("custom", {"type": "verifier.verdict", "capability": "verifier",
                          "status": "completed", "payload": {"result": "fail"}})

    chat_service.graph = MagicMock()
    chat_service.graph.astream = fake_astream

    tokens = []
    async for chunk in chat_service.chat_stream("c1", "hello", settings.MODEL_DASHSCOPE_QWEN):
        tokens.append(chunk)

    assert any(f'"final": "{REPLY_ON_VERIFY_FAILED}"' in t for t in tokens)
    calls = [c.args[0] for c in chat_service.msg_repo.create.call_args_list]
    assistant_saved = [m for m in calls if m.role == "assistant"][0]
    assert assistant_saved.content == REPLY_ON_VERIFY_FAILED


@pytest.mark.asyncio
async def test_chat_stream_error_returns_friendly_message_and_records(chat_service):
    """图运行异常：SSE 只下发友好文案（不含内部细节），agent_runs 落库完整错误+trace_id"""
    conv = Conversation(_id="c1", user_id="anonymous")
    chat_service.conv_repo.get_by_id = AsyncMock(return_value=conv)
    chat_service.msg_repo.list_by_conversation = AsyncMock(return_value=[])
    chat_service.msg_repo.create = AsyncMock(return_value=None)
    chat_service.agent_run_repo.create = AsyncMock(return_value=None)

    async def boom_astream(input, **kwargs):
        """假的 graph.astream：首次迭代即抛 ConnectionError（模拟底层模型不可用）"""
        if False:
            yield  # 仅为了让函数成为 async generator，async for 才能迭代并触发异常
        raise ConnectionError("Ollama down")

    chat_service.graph = MagicMock()
    chat_service.graph.astream = boom_astream

    tokens = []
    # chat_stream 在 yield 友好文案后会重新抛出原异常（供 API 层返回错误状态），
    # 故用 pytest.raises 捕获，同时仍能收集到已下发的 SSE 片段
    with pytest.raises(ConnectionError):
        async for chunk in chat_service.chat_stream("c1", "hello", settings.MODEL_OLLAMA):
            tokens.append(chunk)

    # 用户通道：只有友好文案，绝不包含内部错误信息。
    # 锁定完整友好文案（而非只查 error 键存在），json.dumps 默认分隔符为 ', ' ': '
    assert any(f'"error": "{USER_FRIENDLY_ERROR}"' in t for t in tokens)
    assert all("Ollama" not in t for t in tokens)
    # 管理员通道：agent_runs 落库 error 字段携带完整错误消息与 trace_id
    assert chat_service.agent_run_repo.create.await_count == 1
    run = chat_service.agent_run_repo.create.await_args.args[0]
    assert run.status == "error"
    assert "Ollama down" in run.error
    assert run.trace_id and len(run.trace_id) == 32


@pytest.mark.asyncio
async def test_chat_stream_config_carries_trace_id(chat_service):
    """astream 的 config 必须携带请求级 trace_id（供 emit 与落库串联错误链）"""
    conv = Conversation(_id="c1", user_id="anonymous")
    chat_service.conv_repo.get_by_id = AsyncMock(return_value=conv)
    chat_service.msg_repo.list_by_conversation = AsyncMock(return_value=[])
    chat_service.msg_repo.create = AsyncMock(return_value=None)

    captured = {}

    async def fake_astream(input, **kwargs):
        captured.update(kwargs.get("config", {}))
        yield ("custom", {"type": "verifier.verdict", "capability": "verifier",
                          "status": "completed", "payload": {"result": "pass"}})

    chat_service.graph = MagicMock()
    chat_service.graph.astream = fake_astream

    async for _ in chat_service.chat_stream("c1", "hello", settings.MODEL_OLLAMA):
        pass

    trace_id = captured["configurable"]["trace_id"]
    assert trace_id and len(trace_id) == 32  # uuid4().hex 长度
    assert captured["configurable"]["thread_id"] == "c1"
