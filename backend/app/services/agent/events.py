"""事件系统：能力产出结构化业务事件，chat_service 订阅解耦。

设计要点（规格 v3 第 5 节）：
- emit() 内部自动填充 trace_id（从 LangGraph config 的 configurable 读取）与 seq（全局递增）
- serialize_message() 把 LangChain 消息转成可落库的普通 dict（保留 tool_calls/tool_call_id 等）
- 非流式上下文（单测/离线 invoke）get_stream_writer/get_config 会抛 RuntimeError，
  emit() 降级为 logging.debug，不阻塞执行
"""

import itertools
import logging
import time
from collections import defaultdict
from typing import Any, Callable, TypedDict

from langgraph.config import get_config, get_stream_writer

logger = logging.getLogger(__name__)

# 全局递增序号：供 emit 自动填充事件 seq，保证同一次流输出的事件可被前端按序还原
_seq_counter = itertools.count(1)


class CapabilityEvent(TypedDict, total=False):
    """统一事件信封：所有能力发出的事件遵循同一格式"""
    type: str               # 事件类型："title.completed" / "verifier.verdict" / "agent.tokens"
    capability: str         # 能力标识："title" / "verifier" / "core_agent"
    status: str             # "started" | "progress" | "completed" | "failed"
    payload: dict           # 事件数据（消息必须先经 serialize_message 转 dict）
    trace_id: str           # 请求级追踪 ID（emit 内部自动从 config 读取）
    seq: int                # 全局递增序号（emit 内部自动填充，前端保序）
    timestamp: float        # time.time() 时间戳（emit 内部自动填充）


def _current_trace_id() -> str | None:
    """从当前 LangGraph config 读取 trace_id；非图上下文返回 None"""
    try:
        cfg = get_config()
        return (cfg.get("configurable") or {}).get("trace_id")
    except Exception:
        return None


def _json_safe(obj):
    """把不可 JSON 序列化的值（datetime、自定义对象等）递归转成可序列化形式"""
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    return str(obj)


def serialize_message(msg) -> dict:
    """把 LangChain 消息转成可落库的普通 dict（全链路 trace 的标准格式）。

    设计要点（规格 5.2 + 两轮评审落地）：
    - role 映射：ai→assistant / human→user / tool→tool / 其余原样
    - AIMessage 保留 tool_calls（args 若是 JSON 字符串则转为 dict）与 response_metadata
    - ToolMessage 保留 tool_call_id 与 name（追溯每条工具结果由哪次调用产生）
    - 禁止把 BaseMessage 对象直接放进事件 payload，必须先经本函数序列化
    """
    from langchain_core.messages import AIMessage, ToolMessage

    # 消息 type 只取一次，避免重复 getattr；system 走 passthrough 即可（映射表无需包含）
    msg_type = getattr(msg, "type", "unknown")
    role_map = {"ai": "assistant", "human": "user", "tool": "tool"}
    role = role_map.get(msg_type, msg_type)
    entry: dict[str, Any] = {"role": role, "content": msg.content}
    if getattr(msg, "id", None):
        entry["id"] = msg.id
    if isinstance(msg, ToolMessage):
        if getattr(msg, "name", None):
            entry["name"] = msg.name
        if getattr(msg, "tool_call_id", None):
            entry["tool_call_id"] = msg.tool_call_id
    if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
        calls = []
        for tc in msg.tool_calls:
            args = tc.get("args", {})
            # args 可能是 JSON 字符串（不同版本/模型行为不同），统一转 dict 便于落库解析
            if isinstance(args, str):
                import json

                try:
                    args = json.loads(args)
                except Exception:
                    args = {"raw": args}
            # 保留工具调用 id：与 ToolMessage.tool_call_id 一一对应，
            # 全链路审计才能精确还原"某次调用 → 其结果"的关联（规格 5.2 审计要求）
            calls.append({"name": tc.get("name"), "args": args, "id": tc.get("id")})
        entry["tool_calls"] = calls
        if getattr(msg, "response_metadata", None):
            entry["response_metadata"] = _json_safe(msg.response_metadata)
    return entry


def emit(event_type: str, capability: str, payload: dict | None = None, status: str = "progress") -> None:
    """能力内部统一发事件。

    非流式上下文（单测/离线 invoke）中 get_stream_writer() 会抛 RuntimeError，
    降级为 logging.debug 并返回，不阻塞执行（规格 7.3）。
    """
    try:
        writer = get_stream_writer()
        event = CapabilityEvent(
            type=event_type,
            capability=capability,
            status=status,
            payload=payload or {},
            trace_id=_current_trace_id(),
            seq=next(_seq_counter),
            timestamp=time.time(),
        )
        writer(event)
    except Exception as e:
        # 降级需覆盖"取 writer / 构造信封 / 写入"全过程：任何一环失败都不能阻塞主流程
        logger.debug("emit 降级（非流式上下文）: %s/%s -> %s", capability, event_type, e)


class EventRouter:
    """事件路由器：能力事件 → 订阅处理器分发。

    生命周期约束：每个 chat_stream 请求独立创建，请求结束即销毁，严禁全局单例
    （并发下事件会串流，规格 5.3）。dispatch 为异步：handler 多为 async（Mongo I/O），
    asyncio.gather 并发执行，单个 handler 失败不影响其他 handler 和主循环。
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable[[CapabilityEvent], Any]]] = defaultdict(list)

    def subscribe(self, event_type: str, handler: Callable[[CapabilityEvent], Any]) -> None:
        """订阅事件类型；同类型可订阅多个 handler"""
        self._handlers[event_type].append(handler)

    async def dispatch(self, event: CapabilityEvent) -> None:
        """把事件分发给所有订阅者；逐个隔离异常，未订阅类型记 warning"""
        event_type = event.get("type", "")
        handlers = self._handlers.get(event_type, [])
        if not handlers:
            logger.warning("收到未订阅的事件类型: %s", event_type)
            return

        async def safe_call(handler: Callable[[CapabilityEvent], Any]) -> None:
            """包一层异常隔离：handler 抛错不影响其他 handler"""
            try:
                result = handler(event)
                if hasattr(result, "__await__"):  # 兼容同步/异步 handler
                    await result
            except Exception:
                logger.exception("事件处理器异常: type=%s", event_type)

        import asyncio

        await asyncio.gather(*[safe_call(h) for h in handlers])
