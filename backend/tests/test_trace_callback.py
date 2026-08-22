"""TraceCallbackHandler 单元测试：LLM/工具调用记录 + langgraph_node 归组"""
import pytest

from langchain_core.messages import AIMessage

from app.services.agent.trace_callback import TraceCallbackHandler


@pytest.mark.asyncio
async def test_captures_llm_call_with_node():
    """on_chat_model_start/end 配对 → llm 调用记录，按 langgraph_node 归组"""
    cb = TraceCallbackHandler()
    serialized = {"name": "ChatOpenAI"}
    meta = {"metadata": {"langgraph_node": "agent"}}
    await cb.on_chat_model_start(serialized, [], run_id="r1", **meta)
    await cb.on_chat_model_end(AIMessage(content="hi"), run_id="r1", **meta)
    calls = cb.calls_by_node["agent"]
    assert len(calls) == 1
    assert calls[0]["call_type"] == "llm"
    assert calls[0]["model"] == "ChatOpenAI"
    assert calls[0]["input_tokens"] == 0  # fake 无 usage_metadata，容错为 0


@pytest.mark.asyncio
async def test_captures_llm_usage_metadata():
    """on_chat_model_end 带 usage_metadata：token 数被记录"""
    cb = TraceCallbackHandler()
    meta = {"metadata": {"langgraph_node": "agent"}}
    msg = AIMessage(content="hi", usage_metadata={"input_tokens": 12, "output_tokens": 3, "total_tokens": 15})
    await cb.on_chat_model_start({"name": "qwen"}, [], run_id="r1", **meta)
    await cb.on_chat_model_end(msg, run_id="r1", **meta)
    call = cb.calls_by_node["agent"][0]
    assert call["input_tokens"] == 12
    assert call["output_tokens"] == 3


@pytest.mark.asyncio
async def test_captures_tool_call():
    """on_tool_start/end 配对 → tool 调用记录，含参数与结果"""
    cb = TraceCallbackHandler()
    meta = {"metadata": {"langgraph_node": "tools"}}
    await cb.on_tool_start({"name": "time_tool"}, '{"city": "北京"}', run_id="t1", **meta)
    await cb.on_tool_end("北京晴 25 度", run_id="t1", **meta)
    call = cb.calls_by_node["tools"][0]
    assert call["call_type"] == "tool"
    assert call["tool_name"] == "time_tool"
    assert call["tool_result"] == "北京晴 25 度"