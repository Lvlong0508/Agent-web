"""SSE 序列化：把领域事件（SSEEvent）序列化为 SSE 文本行。

背景：chat_stream 原先在 handler 闭包里直接拼 JSON（_enqueue），业务与传输协议耦合。
本模块把序列化独立出来，handler 只产出领域事件（SSEEvent），不关心协议细节；
测试可脱离 chat_stream 直接逐字节验证输出。

逐字节保真要求：json.dumps 参数必须与原 chat_stream 的 _enqueue 完全一致
（ensure_ascii=False，不设 separators，保留默认的 ', ' 与 ': ' 分隔）。
"""

import json
from dataclasses import dataclass


@dataclass
class SSEEvent:
    """领域事件模型：type 是语义名（title/rewriting/final/error），data 是待序列化载荷。

    type 供生产者（handlers）与未来分发逻辑使用，序列化层只消费 data 字段，
    保持"业务语义名"与"协议载荷"的解耦。
    """
    type: str
    data: dict


class SSESerializer:
    """把 SSEEvent / 错误 / 结束标志序列化为 SSE 文本行（纯同步，无状态）"""

    def serialize(self, event: SSEEvent) -> str:
        """把领域事件序列化为 `data: {...}\n\n` 行"""
        return f"data: {json.dumps(event.data, ensure_ascii=False)}\n\n"

    def serialize_error(self, message: str) -> str:
        """错误事件：用户通道只下发友好文案，不泄漏内部细节"""
        return f"data: {json.dumps({'error': message}, ensure_ascii=False)}\n\n"

    def serialize_done(self) -> str:
        """流结束标志（SSE 标准终止标记）"""
        return "data: [DONE]\n\n"
