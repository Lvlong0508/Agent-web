"""chat 流式会话子包：chat_stream 拆分出的可独立单测单元。

设计（spec 2026-08-17-chat-stream-decouple-design）：
- reply_state：回复状态机（替代闭包 + nonlocal）
- sse_serializer：SSE 序列化（业务与协议解耦）
- handlers：订阅侧业务 handler（标题 / verifier 判定）
- stream_session：会话级可变状态 + 三流消费编排器
本 __init__ 作为包出口，随各文件落地逐步追加重导出。
"""

from app.services.chat.handlers import TitleCompletedHandler, VerdictHandler
from app.services.chat.reply_state import ReplyPhase, ReplyState
from app.services.chat.sse_serializer import SSEEvent, SSESerializer

__all__ = [
    "ReplyPhase", "ReplyState",
    "SSEEvent", "SSESerializer",
    "TitleCompletedHandler", "VerdictHandler",
]
