import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field


class Message(BaseModel):
    """消息 ODM：对应 MongoDB messages 集合"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), alias="_id")
    conversation_id: str    # 所属对话 ID
    role: str               # "user" 或 "assistant"
    content: str            # 消息文本
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}
