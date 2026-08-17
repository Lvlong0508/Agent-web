"""StreamSession 单元测试：token 累积与 trace 收集"""
import pytest
from langchain_core.messages import AIMessage, ToolMessage

from app.services.chat.reply_state import ReplyPhase
from app.services.chat.sse_serializer import SSESerializer
from app.services.chat.stream_session import StreamOrchestrator, StreamSession


def test_initial_state_ready():
    """构造即初始化：空流/立即出错场景下初始状态可用（与旧时序一致）"""
    session = StreamSession(trace_messages=[{"role": "user", "content": "hi"}])
    assert session.reply_state.phase == ReplyPhase.PENDING
    assert session.reply_state.pending_reply == ""
    assert session.trace_messages == [{"role": "user", "content": "hi"}]
    assert session.run_recorded is False
    assert session.sse_events == []


def test_collect_token_accumulates_pending_reply():
    """token 累积到待定回复（验证通过前不推前端）"""
    session = StreamSession()
    session.collect_token("你")
    session.collect_token("好")
    assert session.reply_state.pending_reply == "你好"
    assert session.reply_state.phase == ReplyPhase.PENDING


def test_collect_trace_agent_and_tools():
    """updates 流收集：agent 与 tools 节点消息都进 trace（含工具调用参数）"""
    session = StreamSession()
    updates = {
        "agent": {"messages": [AIMessage(
            content="让我查一下",
            tool_calls=[{"name": "list_expenses", "args": {"page": 1}, "id": "call_1", "type": "tool_call"}],
        )]},
        "tools": {"messages": [ToolMessage(content='{"total": 6}', tool_call_id="call_1", name="list_expenses")]},
    }
    session.collect_trace(updates)
    assert session.trace_messages[0]["role"] == "assistant"
    assert session.trace_messages[0]["tool_calls"][0]["name"] == "list_expenses"
    assert session.trace_messages[1]["role"] == "tool"
    assert session.trace_messages[1]["tool_call_id"] == "call_1"


def test_collect_trace_verifier():
    """updates 流收集：质检输入与判定都进 trace（含 role=input_verdict / verdict）"""
    session = StreamSession()
    updates = {
        "verifier": {
            "verdict_input": [{"role": "user", "content": "hello"}],
            "verdict": {"result": "pass", "reason": "OK"},
        }
    }
    session.collect_trace(updates)
    assert session.trace_messages[0] == {"role": "input_verdict", "content": [{"role": "user", "content": "hello"}]}
    assert session.trace_messages[1] == {"role": "verdict", "content": {"result": "pass", "reason": "OK"}}


def test_collect_trace_ignores_missing_sections():
    """updates 流缺省节点段（无 agent/tools/verifier）时不应抛错"""
    session = StreamSession()
    session.collect_trace({"some_node": {"messages": []}})
    assert session.trace_messages == []


def _make_orchestrator():
    """构造一个可直接调用 _handle_messages 的编排器（graph 传 None 不触发）"""
    session = StreamSession()
    return StreamOrchestrator(graph=None, session=session, serializer=SSESerializer())


def test_handle_messages_skips_non_agent_node():
    """messages 流：非 agent 节点（如 generate_title）的输出不累积为回复"""
    orch = _make_orchestrator()
    chunk = AIMessage(content="标题")
    orch._handle_messages((chunk, {"langgraph_node": "generate_title"}))
    assert orch._session.reply_state.pending_reply == ""


def test_handle_messages_skips_streaming_tool_call():
    """messages 流：含 tool_call_chunks 的流式工具调用轮不累积为回复"""
    orch = _make_orchestrator()
    chunk = AIMessage(content="", tool_call_chunks=[{"name": "list_expenses"}])
    orch._handle_messages((chunk, {"langgraph_node": "agent"}))
    assert orch._session.reply_state.pending_reply == ""


def test_handle_messages_skips_complete_tool_call():
    """messages 流：含 tool_calls 的完整工具调用轮不累积为回复"""
    orch = _make_orchestrator()
    chunk = AIMessage(content="", tool_calls=[
        {"name": "list_expenses", "args": {}, "id": "call_1", "type": "tool_call"},
    ])
    orch._handle_messages((chunk, {"langgraph_node": "agent"}))
    assert orch._session.reply_state.pending_reply == ""


def test_handle_messages_accumulates_text_token():
    """messages 流：agent 节点的纯文本 token 累积为待定回复"""
    orch = _make_orchestrator()
    chunk = AIMessage(content="你好")
    orch._handle_messages((chunk, {"langgraph_node": "agent"}))
    assert orch._session.reply_state.pending_reply == "你好"