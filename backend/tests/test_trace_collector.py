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


def test_input_message_truncation():
    """单条消息超 8KB：content 截断且标 truncated 标记"""
    from app.services.chat.trace_collector import _truncate_message
    result = _truncate_message({"role": "user", "content": "x" * 9000})
    assert result["truncated"] is True
    assert len(result["content"]) < 9000              # 已被截断
    assert result["content"].endswith("...[已截断]")  # 截断有痕
    assert result["content"].startswith("x" * 8192)   # 保留前 limit 字节


def test_input_messages_over_50_keeps_recent():
    """messages 超 50 条：保留最近 50 条 + input.truncated=True"""
    c = TraceCollector("t1")
    msgs = [{"role": "user", "content": f"m{i}"} for i in range(60)]
    c.process_debug_event(_task("agent", input_={"messages": msgs}))
    c.process_debug_event(_task_result("agent", "2026-08-22T00:00:00.200Z"))
    step = c.raw_steps[0]
    assert step["input"]["truncated"] is True
    assert len(step["input"]["messages"]) == 50
    assert step["input"]["messages"][-1]["content"] == "m59"


def test_attach_calls_to_step():
    """callback 记录的 Call 挂到同名节点 Step"""
    c = TraceCollector("t1")
    c.process_debug_event(_task("agent"))
    c.process_debug_event(_task_result("agent", "2026-08-22T00:00:00.200Z"))
    c.attach_calls({"agent": [{"call_id": "call_001", "call_type": "llm",
                               "model": "qwen-max", "input_tokens": 10, "output_tokens": 5}]})
    assert len(c.raw_steps[0]["calls"]) == 1
    assert c.raw_steps[0]["calls"][0]["model"] == "qwen-max"


def test_attach_calls_sets_metrics():
    """挂载 Call 后 Step.metrics 汇总 token 数（供管理员快速看成本）"""
    c = TraceCollector("t1")
    c.process_debug_event(_task("agent"))
    c.process_debug_event(_task_result("agent", "2026-08-22T00:00:00.200Z"))
    c.attach_calls({"agent": [{"call_type": "llm", "input_tokens": 10, "output_tokens": 5},
                              {"call_type": "llm", "input_tokens": 3, "output_tokens": 2}]})
    step = c.raw_steps[0]
    assert step["metrics"]["input_tokens"] == 13
    assert step["metrics"]["output_tokens"] == 7