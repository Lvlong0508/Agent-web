from __future__ import annotations  # 延迟注解求值：方法名为 list 会遮蔽内置 list，避免类型注解在运行时把方法当列表下标

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.agent_run import AgentRun
from app.repositories.agent_run_repo import AgentRunRepo
from app.schemas.agent_run import AgentRunPage


class AgentRunService:
    """agent 运行记录业务层：屏蔽 Mongo 细节，对外提供插入/分页查询/批量删除。

    运行记录是管理员排障数据（规格 7.1），查询不做强制的 user_id 隔离，
    过滤是可选条件而非安全边界。
    """

    def __init__(self, db: AsyncIOMotorDatabase):
        # 数据访问全部委托 AgentRunRepo，service 只做入参组装与业务规则
        self.repo = AgentRunRepo(db)

    async def create(
        self,
        conversation_id: str,
        user_id: str,
        model: str,
        status: str = "ok",
        messages: list[dict] | None = None,
        trace_id: str = "",
        error: str | None = None,
    ) -> AgentRun:
        """插入一条运行记录：内部构造 AgentRun 落库，返回完整对象。
        chat_service 不再自行构造模型对象，字段语义收敛到 service 层"""
        run = AgentRun(
            conversation_id=conversation_id,
            user_id=user_id,
            model=model,
            status=status,
            messages=messages or [],  # 缺省给空列表，避免 None 落库
            trace_id=trace_id,
            error=error,
        )
        return await self.repo.create(run)

    async def list(
        self,
        page: int = 1,
        page_size: int = 20,
        user_id: str | None = None,
        conversation_id: str | None = None,
    ) -> AgentRunPage:
        """分页查询运行记录：默认全量，可按 user_id / conversation_id 可选过滤。
        page 下限 1、page_size 钳到 1~100（防恶意大值）；创建时间倒序（最新在前）。"""
        # 参数钳制：页码至少 1，每页条数限制在 1~100
        page = max(page, 1)
        page_size = min(max(page_size, 1), 100)
        # 组装 Mongo 过滤条件：只有显式传入的过滤维度才加进去
        filters: dict = {}
        if user_id:
            filters["user_id"] = user_id
        if conversation_id:
            filters["conversation_id"] = conversation_id
        items, total = await self.repo.list_paged(filters, page, page_size)
        return AgentRunPage(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=(total + page_size - 1) // page_size,
        )

    async def delete_many(self, run_ids: list[str]) -> int:
        """批量删除运行记录：空列表直接返回 0（不发无意义查询）；
        不存在的 id 由 Mongo $in 静默跳过，返回实际删除条数"""
        if not run_ids:
            return 0
        return await self.repo.delete_many(run_ids)