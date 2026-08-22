"""三层模型单元测试：默认值与字段"""
import pytest

from app.models.trace import TraceCall, TraceStep


def test_trace_step_defaults():
    """Step 默认值：calls 空列表、metrics/error_info 为 None、duration 为 0"""
    step = TraceStep(step_id="step_001", node_name="agent", step_type="agent",
                     status="success")
    assert step.duration_ms == 0
    assert step.calls == []
    assert step.metrics is None
    assert step.error_info is None


def test_trace_call_llm():
    """LLM 调用：model/tokens/finish_reason 字段"""
    call = TraceCall(call_id="call_001", call_type="llm", model="qwen-max",
                     input_tokens=100, output_tokens=20, finish_reason="stop")
    assert call.call_type == "llm"
    assert call.input_tokens == 100


def test_trace_call_tool():
    """工具调用：tool_name/result 字段"""
    call = TraceCall(call_id="call_002", call_type="tool", tool_name="time_tool",
                     tool_call_id="call_1", tool_result="北京晴 25 度")
    assert call.tool_call_id == "call_1"


def test_agent_run_new_fields_defaults():
    """AgentRun 新增字段默认值：汇总为 0、verdict None、steps 空列表"""
    from app.models.agent_run import AgentRun
    run = AgentRun(conversation_id="c1", user_id="u1", model="ollama")
    assert run.duration_ms == 0
    assert run.total_input_tokens == 0
    assert run.verdict is None
    assert run.retry_count == 0
    assert run.steps == []