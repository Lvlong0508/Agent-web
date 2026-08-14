from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.conversation import Conversation


class ConversationRepo:
    """对话集合的数据访问层：处理 MongoDB conversations 文档的 CRUD"""

    COLLECTION = "conversations"

    def __init__(self, db: AsyncIOMotorDatabase):
        self.collection = db[self.COLLECTION]

    async def create(self, user_id: str) -> Conversation:
        """创建空对话，返回带生成 ID 的 Conversation 对象"""
        conv = Conversation(user_id=user_id)
        await self.collection.insert_one(conv.model_dump(by_alias=True))
        return conv

    async def list_by_user(self, user_id: str) -> list[Conversation]:
        """按 updated_at 降序返回用户的所有对话"""
        cursor = self.collection.find({"user_id": user_id}).sort("updated_at", -1)
        docs = await cursor.to_list(length=None)
        return [Conversation(**doc) for doc in docs]

    async def get_by_id(self, conv_id: str, user_id: str) -> Conversation | None:
        """根据对话 ID + 归属用户获取对话；不属于该用户时返回 None（查询层防越权）"""
        doc = await self.collection.find_one({"_id": conv_id, "user_id": user_id})
        return Conversation(**doc) if doc else None

    async def update_title(self, conv_id: str, title: str):
        """更新对话标题和 updated_at 时间戳"""
        await self.collection.update_one(
            {"_id": conv_id},
            {"$set": {"title": title, "updated_at": datetime.now(timezone.utc)}},
        )

    async def delete(self, conv_id: str):
        """删除对话（级联删除消息由调用方负责）"""
        await self.collection.delete_one({"_id": conv_id})
