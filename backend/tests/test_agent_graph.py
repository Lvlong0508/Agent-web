from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage
from langgraph.graph import END

from app.services.agent_graph import (
    AgentState,
    build_agent_graph,
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
