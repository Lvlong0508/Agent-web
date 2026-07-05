from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.message import Message


class MessageRepo:
    """消息集合的数据访问层：处理 MongoDB messages 文档的 CRUD"""

    COLLECTION = "messages"

    def __init__(self, db: AsyncIOMotorDatabase):
        self.collection = db[self.COLLECTION]

    async def create(self, message: Message) -> Message:
        """插入一条消息并返回"""
        await self.collection.insert_one(message.model_dump(by_alias=True))
        return message

    async def list_by_conversation(self, conversation_id: str) -> list[Message]:
        """按 created_at 升序返回对话的全部消息"""
        cursor = self.collection.find(
            {"conversation_id": conversation_id}
        ).sort("created_at", 1)
        docs = await cursor.to_list(length=None)
        return [Message(**doc) for doc in docs]

    async def delete_by_conversation(self, conversation_id: str):
        """删除某对话下的所有消息"""
        await self.collection.delete_many({"conversation_id": conversation_id})
