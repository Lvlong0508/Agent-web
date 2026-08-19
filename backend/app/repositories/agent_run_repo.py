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

    async def list_paged(
        self,
        filters: dict,
        page: int,
        page_size: int,
    ) -> tuple[list[AgentRun], int]:
        """分页查询运行记录：先统计总数，再按创建时间倒序取当前页。
        filters 是 Mongo 过滤条件（空 dict = 全量），供管理端按条件检索。"""
        # 先 count_documents 统计匹配总数，用于计算总页数
        total = await self.collection.count_documents(filters)
        # 再按 created_at 倒序（最新在前）skip/limit 取当前页，避免全量加载
        cursor = (
            self.collection.find(filters)
            .sort("created_at", -1)
            .skip((page - 1) * page_size)
            .limit(page_size)
        )
        docs = await cursor.to_list(length=page_size)
        return [AgentRun(**doc) for doc in docs], total

    async def delete_many(self, run_ids: list[str]) -> int:
        """按 _id 批量删除（$in），不存在的 id 静默跳过；返回实际删除条数"""
        result = await self.collection.delete_many({"_id": {"$in": run_ids}})
        return result.deleted_count
