from datetime import datetime
from pydantic import BaseModel


# -------------------- 请求体 --------------------


class SendMessageRequest(BaseModel):
    """发送消息请求体"""
    content: str
    model: str   # 模型选择名（如 ollama-qwen3.5 / qwen3.7-flash）


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
