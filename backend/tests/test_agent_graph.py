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
)


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
    """测试最后消息无工具调用时路由到 END"""
    state = {"messages": [AIMessage(content="你好")]}
    assert should_continue(state) == END


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

    def fake_create_llm(streaming: bool = True, model: str = ""):
        received_models.append(model)
        return title_llm if not streaming else agent_llm

    graph = build_agent_graph(conv_repo)
    full_text = ""
    with patch("app.services.agent_graph.create_llm", side_effect=fake_create_llm):
        async for item in graph.astream(
            {
                "messages": [HumanMessage(content="hi")],
                "conv_id": "c1",
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
    # agent 节点的回复以 token 形式流式拼出
    assert "你好，世界" in full_text
    # 图内节点应按所选模型创建 LLM（标题节点 + agent 节点各调用一次）
    assert received_models == [settings.MODEL_DASHSCOPE_QWEN] * 2


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

    def fake_create_llm(streaming: bool = True, model: str = ""):
        received_models.append(model)
        return title_llm if not streaming else agent_llm

    graph = build_agent_graph(conv_repo)
    full_text = ""
    with patch("app.services.agent_graph.create_llm", side_effect=fake_create_llm):
        async for item in graph.astream(
            {
                "messages": [HumanMessage(content="hi")],
                "conv_id": "c1",
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
    # 图内节点应按所选模型创建 LLM（标题节点 + agent 节点各调用一次）
    assert received_models == [settings.MODEL_DASHSCOPE_QWEN] * 2


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


def test_create_llm_unknown_model_raises():
    """测试非空未知选择名抛 ValueError，避免静默回退掩盖配置漂移"""
    with pytest.raises(ValueError):
        create_llm(model="qwen3.7-flsh")  # 拼错的选择名


def test_create_llm_default_falls_back_to_ollama():
    """测试未指定 model 时回退本地 Ollama（向后兼容）"""
    with patch("app.services.agent_graph.ChatOpenAI") as mock_cls:
        create_llm(streaming=True)
    mock_cls.assert_called_once()
    kwargs = mock_cls.call_args.kwargs
    assert kwargs["base_url"] == settings.OLLAMA_BASE_URL + "/v1"
    assert kwargs["model"] == settings.LLM_MODEL
    assert kwargs["api_key"] == "ollama"
