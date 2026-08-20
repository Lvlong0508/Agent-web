"""订阅侧业务 handler：把能力事件转成领域事件（SSEEvent）并驱动 ReplyState。

设计要点（spec 2026-08-17-chat-stream-decouple-design）：
- handler 只产出领域事件（写入 out 队列），不直接拼 JSON（序列化交给 SSESerializer）
- handler 通过构造注入依赖（ReplyState 引用、out 输出队列），可独立单测
- 依赖注入方式替代原 chat_stream 的闭包 + nonlocal：状态转移路径显式可追踪

注意：out 队列是 chat_stream 在 orchestration 开始时创建并注入的普通 list，
与 StreamSession.sse_events 指向同一对象，主循环据此产出 SSE。
"""

from app.services.chat.reply_state import ReplyState
from app.services.chat.sse_serializer import SSEEvent
from app.services.agent import (
    PLANNER_COMPLETED_EVENT,
    PLANNER_FAILED_EVENT,
)


class TitleCompletedHandler:
    """处理 title.completed：标题非空才产出 title 事件（避免无谓消息）"""

    def __init__(self, out: list[SSEEvent]):
        """out：领域事件输出队列（chat_stream 注入，与 StreamSession.sse_events 同对象）"""
        self._out = out

    async def handle(self, event: dict) -> None:
        """读取事件载荷中的标题；非空则产出 title 领域事件"""
        title = (event.get("payload") or {}).get("title")
        if title:
            self._out.append(SSEEvent(type="title", data={"title": title}))


class VerdictHandler:
    """处理 verifier.verdict：按判定结果驱动 ReplyState 转移并产出对应事件"""

    def __init__(self, state: ReplyState, fail_text: str, out: list[SSEEvent]):
        """state：回复状态机引用（构造注入）；fail_text：fail 判定的固定文案；
        out：领域事件输出队列"""
        self._state = state
        self._fail_text = fail_text
        self._out = out

    async def handle(self, event: dict) -> None:
        """按 result 分派：retry→清空待定回复进重写轮；pass/fail→生成最终版。

        状态转移全部经 ReplyState 的语义化方法，非法转移在状态机内部抛错。
        """
        result = (event.get("payload") or {}).get("result")
        if result == "retry":
            self._state.on_retry()
            self._out.append(SSEEvent(type="rewriting", data={"rewriting": True}))
        elif result == "pass":
            self._state.on_pass()
            self._out.append(SSEEvent(type="final", data={"final": self._state.full_response}))
        elif result == "fail":
            self._state.on_fail(self._fail_text)
            self._out.append(SSEEvent(type="final", data={"final": self._state.full_response}))

class PlannerHandler:
    """处理 planner.completed / planner.failed：把规划状态推给前端进度展示。

    规划发生在 agent 推理之前，前端可据此显示"正在规划 / 规划完成 / 规划失败"。
    统一归一为 type="planner"，data 含 status/reason/cost_time_ms，前端单一解析入口。
    """

    def __init__(self, out: list[SSEEvent]):
        """out：领域事件输出队列（chat_stream 注入，与 StreamSession.sse_events 同对象）"""
        self._out = out

    async def handle(self, event: dict) -> None:
        """把 planner 事件归一为 SSEEvent(type="planner")；payload 缺失则忽略"""
        payload = event.get("payload") or {}
        if not payload:
            return
        # 事件类型区分完成/失败：completed 的 payload.status 是 planned/skipped，
        # failed 的 status 固定 failed（节点 emit 时已带 status="failed"）
        event_type = event.get("type", "")
        if event_type == PLANNER_FAILED_EVENT:
            status = "failed"
        else:
            status = payload.get("status", "planned")
        self._out.append(SSEEvent(type="planner", data={
            "status": status,
            "reason": payload.get("reason", ""),
            "cost_time_ms": payload.get("cost_time_ms", 0),
        }))