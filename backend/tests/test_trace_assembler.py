"""组装器测试：raw_steps → AgentRun 三层文档"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.models.agent_run import AgentRun
from app.services.agent_run_service import AgentRunService


def _raw_planner_step():
    return {"step_id": "step_001", "node_name": "planner", "step_type": "planner",
            "status": "success", "start_time": "2026-08-22T00:00:00.100Z",
            "end_time": "2026-08-22T00:00:00.200Z", "duration_ms": 100,
            "input": {"messages": []}, "output": {"messages": [
                {"role": "planner", "content": "规划完成"}]},
            "error_info": None, "truncated": False, "calls": []}


def _raw_agent_step():
    return {"step_id": "step_002", "node_name": "agent", "step_type": "agent",
            "status": "success", "start_time": "2026-08-22T00:00:00.200Z",
            "end_time": "2026-08-22T00:00:00.900Z", "duration_ms": 700,
            "input": {"messages": []}, "output": {"messages": [
                {"role": "assistant", "content": "你好"}]},
            "error_info": None, "truncated": False,
            "calls": [{"call_id": "call_001", "call_type": "llm", "model": "qwen-max",
                       "input_tokens": 100, "output_tokens": 20, "finish_reason": "stop"}]}


def _raw_verifier_step():
    return {"step_id": "step_003", "node_name": "verifier", "step_type": "verifier",
            "status": "success", "start_time": "2026-08-22T00:00:00.900Z",
            "end_time": "2026-08-22T00:01:00.000Z", "duration_ms": 100,
            "input": {"messages": []}, "output": {"verification_result": "pass",
                "rewrite_count": 0, "verdict": {"is_accurate": True, "issues": ""}},
            "error_info": None, "truncated": False, "calls": []}


@pytest.mark.asyncio
async def test_create_assemble_three_layers():
    """raw_steps + entry → AgentRun：steps 含 entry 与各节点，汇总正确"""
    service = AgentRunService(MagicMock())
    service.repo.create = AsyncMock(return_value=None)
    entry = {"step_id": "step_000", "node_name": "entry", "step_type": "entry", "status": "success",
             "input": {"messages": [{"role": "system", "content": "你是助手"}]},
             "output": {}, "calls": [], "start_time": "2026-08-22T00:00:00.000Z",
             "end_time": "2026-08-22T00:00:00.100Z", "duration_ms": 100,
             "error_info": None, "truncated": False}
    await service.create(conversation_id="c1", user_id="u1", model="ollama",
                         raw_steps=[_raw_planner_step(), _raw_agent_step(), _raw_verifier_step()],
                         entry=entry, trace_id="t1")
    run = service.repo.create.await_args.args[0]
    assert isinstance(run, AgentRun)
    assert [s.step_type for s in run.steps] == ["entry", "planner", "agent", "verifier"]
    assert run.total_input_tokens == 100
    assert run.total_output_tokens == 20
    assert run.verdict == "pass"
    assert run.retry_count == 0
    assert run.duration_ms == 60000  # entry.start → verifier.end