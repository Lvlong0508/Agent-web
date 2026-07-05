import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field


class Conversation(BaseModel):
    """对话 ODM：对应 MongoDB conversations 集合"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), alias="_id")
    user_id: str            # 所属用户的 ID（关联 MySQL users 表）
    title: str = ""          # 对话标题，首次回复后由 LLM 自动生成
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}
