"""自适应全链路记录收集器（chat 领域）：消费 LangGraph debug 流产出原始 Step 记录。

核心设计：不硬编码任何节点名——debug 流的 task/task_result 事件天然携带节点名，
新增/删除/改名节点记录逻辑零改动（spec §5.1）。所有异常静默吞掉，不阻塞主流程。
"""

from datetime import datetime
from typing import Any

# 输入存储策略阈值：单条消息序列化超 8KB 截断；messages 超 50 条保留最近 50 条
MAX_MESSAGE_CHARS = 8 * 1024
MAX_INPUT_MESSAGES = 50


def _parse_ts(ts: str | None) -> datetime | None:
    """把 debug 流 ISO 时间戳解析为 datetime；解析失败返回 None（防御性）"""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _truncate_message(msg: dict, limit: int = MAX_MESSAGE_CHARS) -> dict:
    """单条消息内容超限时截断并打标记（截断有痕，管理员可感知）"""
    if not isinstance(msg, dict) or not isinstance(msg.get("content"), str):
        return msg
    if len(msg["content"]) <= limit:
        return msg
    return {**msg, "content": msg["content"][:limit] + "...[已截断]", "truncated": True}


class TraceCollector:
    """消费 debug 流，按 task/task_result 配对组装原始 Step 记录（dict 形式）。

    raw_steps 用 dict 而非 TraceStep 模型：chat 领域不依赖 run 领域的数据模型，
    组装成 AgentRun 的职责在 AgentRunService（run 领域）完成。
    """

    def __init__(self, trace_id: str):
        self.trace_id = trace_id
        self.raw_steps: list[dict] = []
        self._pending: dict[str, dict] = {}   # task id → task 事件信息
        self._seq = 0

    def process_debug_event(self, event: dict) -> None:
        """处理一个 debug 流事件（task 或 task_result）；解析异常静默跳过"""
        try:
            etype = event.get("type")
            payload = event.get("payload") or {}
            if etype == "task":
                name = payload.get("name", "unknown")
                self._pending[payload.get("id", "")] = {
                    "node_name": name,
                    "start_time": _parse_ts(event.get("timestamp")),
                    "input": self._guard_input(payload.get("input")),
                }
            elif etype == "task_result":
                self._finish_step(payload, event.get("timestamp"))
        except Exception:
            pass

    def _finish_step(self, payload: dict, end_ts: str | None) -> None:
        """task_result 到达：配对 pending，产出 Step 记录（含耗时）"""
        pending = self._pending.pop(payload.get("id", ""), None)
        if pending is None:
            return
        end = _parse_ts(end_ts)
        duration = 0
        if pending["start_time"] and end:
            duration = int((end - pending["start_time"]).total_seconds() * 1000)
        self._seq += 1
        error = payload.get("error")
        self.raw_steps.append({
            "step_id": f"step_{self._seq:03d}",
            "node_name": pending["node_name"],
            "step_type": pending["node_name"],
            "status": "error" if error else "success",
            "start_time": pending["start_time"],
            "end_time": end,
            "duration_ms": duration,
            "input": pending["input"],
            "output": payload.get("result") or {},
            "error_info": {"type": type(error).__name__, "message": str(error)} if error else None,
            "truncated": pending["input"].get("truncated", False),
            "calls": [],
        })

    def attach_calls(self, calls_by_node: dict[str, list[dict]]) -> None:
        """把 callback 记录的 Call 挂到同名节点 Step；无对应 Step 的节点记录丢弃。"""
        try:
            by_node = {s["node_name"]: s for s in self.raw_steps}
            for node_name, calls in (calls_by_node or {}).items():
                step = by_node.get(node_name)
                if step is None:
                    continue
                step["calls"].extend(calls)
                # 汇总该节点 token 到 metrics，列表页无需展开 calls 即可看成本
                in_tok = sum(c.get("input_tokens", 0) for c in calls if c.get("call_type") == "llm")
                out_tok = sum(c.get("output_tokens", 0) for c in calls if c.get("call_type") == "llm")
                step["metrics"] = {"input_tokens": in_tok, "output_tokens": out_tok}
        except Exception:
            pass

    @staticmethod
    def _guard_input(state: Any) -> dict:
        """输入存储策略：只保留 messages 与状态字段名，不存完整 state 快照。

        目的：防单条 AgentRun 文档逼近 MongoDB 16MB 上限（spec §5.2）。
        messages 超限截断并打标记（截断有痕，管理员可感知）。
        """
        if not isinstance(state, dict):
            return {}
        msgs = state.get("messages") or []
        truncated = len(msgs) > MAX_INPUT_MESSAGES
        kept = msgs[-MAX_INPUT_MESSAGES:] if truncated else msgs
        # 逐条应用单消息截断（超长 content 截断并标记）
        kept = [_truncate_message(m) for m in kept]
        return {"messages": kept, "truncated": truncated,
                "state_keys": sorted(k for k in state.keys() if k != "messages")}