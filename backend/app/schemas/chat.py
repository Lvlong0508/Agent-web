from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.config.settings import settings


# -------------------- 请求体 --------------------


class SendMessageRequest(BaseModel):
    """发送消息请求体"""
    content: str
    # 模型选择名：仅允许两个合法值，未传时缺省本地 Ollama（与图内回退设计一致）
    model: Literal[settings.MODEL_OLLAMA, settings.MODEL_DASHSCOPE_QWEN] = settings.MODEL_OLLAMA
    # 深度思考开关（仅通义千问生效）：默认关闭，加快回复流式输出；开启后更深入但更慢
    thinking: bool = False


# -------------------- 响应体 --------------------


class ConversationResponse(BaseModel):
    """对话信息响应"""
    id: str
    title: str
    created_at: datetime


class ConversationListItem(BaseModel):
    """对话列表项（含 updated_at）"""
    id: str
    title: str
    created_at: datetime
    updated_at: datetime


class MessageResponse(BaseModel):
    """消息响应"""
    role: str       # "user" 或 "assistant"
    content: str    # 消息文本
    created_at: datetime


class DeleteResponse(BaseModel):
    """删除操作响应"""
    detail: str = "deleted"
