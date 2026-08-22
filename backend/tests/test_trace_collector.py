"""TraceCollector 单元测试：debug 流 task/task_result → raw_steps"""
import pytest

from app.services.chat.trace_collector import TraceCollector


def _task(name, ts="2026-08-22T00:00:00.100Z", input_=None):
    return {"type": "task", "step": 1, "timestamp": ts,
            "payload": {"id": f"id-{name}", "name": name,
                        "input": input_ or {"messages": []}, "triggers": []}}


def _task_result(name, ts, result=None, error=None):
    return {"type": "task_result", "step": 1, "timestamp": ts,
            "payload": {"id": f"id-{name}", "name": name,
                        "result": result or {}, "error": error}}


def test_collects_node_pair():
    """task + task_result 配对 → 一条 Step：含节点名、耗时、输出"""
    c = TraceCollector("t1")
    c.process_debug_event(_task("agent", "2026-08-22T00:00:00.100Z"))
    c.process_debug_event(_task_result("agent", "2026-08-22T00:00:00.200Z",
                                       result={"messages": [{"role": "assistant", "content": "hi"}]}))
    assert len(c.raw_steps) == 1
    step = c.raw_steps[0]
    assert step["node_name"] == "agent"
    assert step["status"] == "success"
    assert step["duration_ms"] == 100
    assert step["output"]["messages"][0]["content"] == "hi"


def test_collects_node_error():
    """task_result 带 error → Step.status=error + error_info"""
    c = TraceCollector("t1")
    c.process_debug_event(_task("planner"))
    c.process_debug_event(_task_result("planner", "2026-08-22T00:00:00.300Z", error="boom"))
    step = c.raw_steps[0]
    assert step["status"] == "error"
    assert step["error_info"]["message"] == "boom"


def test_parallel_branch_nodes_kept():
    """旁路节点（generate_title）自动收集，不因主链路而丢失"""
    c = TraceCollector("t1")
    c.process_debug_event(_task("generate_title"))
    c.process_debug_event(_task("planner"))
    c.process_debug_event(_task_result("planner", "2026-08-22T00:00:00.150Z"))
    c.process_debug_event(_task_result("generate_title", "2026-08-22T00:00:00.200Z"))
    # 并行节点按 task_result 完成顺序记录（planner 先完成先入列）
    assert [s["node_name"] for s in c.raw_steps] == ["planner", "generate_title"]