from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.agent_run import AgentRun


class AgentRunRepo:
    """agent 运行记录的数据访问层：处理 MongoDB agent_runs 集合的 CRUD"""

    COLLECTION = "agent_runs"

    def __init__(self, db: AsyncIOMotorDatabase):
        self.collection = db[self.COLLECTION]

    async def create(self, run: AgentRun) -> AgentRun:
        """插入一条运行记录并返回"""
        await self.collection.insert_one(run.model_dump(by_alias=True))
        return run

    async def list_by_conversation(self, conversation_id: str) -> list[AgentRun]:
        """按 created_at 升序返回对话的全部运行记录（一条 = 一轮）"""
        cursor = self.collection.find(
            {"conversation_id": conversation_id}
        ).sort("created_at", 1)
        docs = await cursor.to_list(length=None)
        return [AgentRun(**doc) for doc in docs]
