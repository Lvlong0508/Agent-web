"""Call 级全链路采集：捕获 LLM/工具调用记录，按节点归组。

langgraph_node 取自 callback 事件 metadata，与 debug 流 Step 关联（spec §2.1）。
所有字段防御性取值：真实模型缺失 usage_metadata 时 token 记 0，不报错。
"""

import time
from collections import defaultdict

from langchain_core.callbacks import AsyncCallbackHandler


class TraceCallbackHandler(AsyncCallbackHandler):
    """记录每次 LLM 调用与工具调用的元数据，按 langgraph_node 归组供归并"""

    def __init__(self):
        self.calls_by_node: dict[str, list[dict]] = defaultdict(list)
        self._pending: dict[str, dict] = {}   # run_id → 开始记录
        self._seq = 0

    def _node_of(self, kwargs) -> str:
        """从 callback kwargs 提取 langgraph_node；缺省 unknown"""
        return (kwargs.get("metadata") or {}).get("langgraph_node", "unknown")

    async def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs):
        self._pending[run_id] = {
            "call_id": f"call_{self._seq:03d}",
            "call_type": "llm",
            "model": (serialized or {}).get("name"),
            "start_time": time.time(),
            "node": self._node_of(kwargs),
        }

    async def on_chat_model_end(self, response, *, run_id, **kwargs):
        pending = self._pending.pop(run_id, None)
        if pending is None:
            return
        usage = getattr(response, "usage_metadata", None) or {}
        pending.update({
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
            "finish_reason": (getattr(response, "response_metadata", {}) or {}).get("finish_reason"),
            "duration_ms": int((time.time() - pending["start_time"]) * 1000),
        })
        self.calls_by_node[pending["node"]].append(pending)

    async def on_tool_start(self, serialized, input_str, *, run_id, **kwargs):
        self._pending[run_id] = {
            "call_id": f"call_{self._seq:03d}",
            "call_type": "tool",
            "tool_name": (serialized or {}).get("name"),
            "start_time": time.time(),
            "node": self._node_of(kwargs),
        }

    async def on_tool_end(self, output, *, run_id, **kwargs):
        pending = self._pending.pop(run_id, None)
        if pending is None:
            return
        pending.update({
            "tool_result": str(output)[:2000],
            "duration_ms": int((time.time() - pending["start_time"]) * 1000),
        })
        self.calls_by_node[pending["node"]].append(pending)