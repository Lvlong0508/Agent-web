from __future__ import annotations  # 延迟注解求值：方法名为 list 会遮蔽内置 list，避免类型注解在运行时把方法当列表下标

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.agent_run import AgentRun
from app.models.trace import TraceCall, TraceStep
from app.repositories.agent_run_repo import AgentRunRepo
from app.schemas.agent_run import AgentRunPage


class AgentRunService:
    """agent 运行记录业务层：屏蔽 Mongo 细节，对外提供插入/分页查询/批量删除。

    运行记录是管理员排障数据（规格 7.1），查询不做强制的 user_id 隔离，
    过滤是可选条件而非安全边界。
    三层结构组装（spec 2026-08-22）：chat 侧产出的 raw_steps（原始 Step dict）
    在本层组装为 TraceStep 模型并生成运行级汇总，落库 AgentRun.steps。
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
        raw_steps: list[dict] | None = None,
        entry: dict | None = None,
        trace_id: str = "",
        error: str | None = None,
    ) -> AgentRun:
        """插入一条运行记录：内部构造 AgentRun 落库，返回完整对象。

        raw_steps/entry：三层结构的原始 Step 记录（chat 侧 TraceCollector 产出），
        非空时组装为 steps 并生成运行级汇总；兼容旧 messages 参数（退化路径）。
        """
        if raw_steps:
            steps = self._assemble_steps(raw_steps, entry)
            summary = self._summarize(steps)
            run = AgentRun(
                conversation_id=conversation_id,
                user_id=user_id,
                model=model,
                status=status,
                messages=[],
                trace_id=trace_id,
                error=error,
                steps=steps,
                **summary,
            )
        else:
            # 退化路径：旧 messages 直存（历史调用方/测试兼容）
            run = AgentRun(
                conversation_id=conversation_id,
                user_id=user_id,
                model=model,
                status=status,
                messages=messages or [],
                trace_id=trace_id,
                error=error,
            )
        return await self.repo.create(run)

    def _assemble_steps(self, raw_steps: list[dict], entry: dict | None) -> list[TraceStep]:
        """把原始 Step dict 列表组装为 TraceStep 模型；entry 插到首位。"""
        steps = []
        if entry:
            steps.append(TraceStep(**{k: v for k, v in entry.items() if k != "truncated"}))
        for raw in raw_steps or []:
            data = {k: v for k, v in raw.items() if k != "truncated"}
            data["calls"] = [TraceCall(**c) for c in data.get("calls", [])]
            # role 归位（spec §4.4）：planner 节点的规划 SystemMessage 序列化为
            # role=system（name=planner），此处还原为语义 role=planner，前端依赖该值
            output = data.get("output") or {}
            if data["step_type"] == "planner" and "messages" in output:
                for m in output["messages"]:
                    if isinstance(m, dict) and m.get("role") == "system" and m.get("name") == "planner":
                        m["role"] = "planner"
            steps.append(TraceStep(**data))
        return steps

    def _summarize(self, steps: list[TraceStep]) -> dict:
        """运行级汇总：总耗时、总 token、最终 verdict、重写次数"""
        if not steps:
            return {"duration_ms": 0, "total_input_tokens": 0, "total_output_tokens": 0,
                    "verdict": None, "retry_count": 0}
        start = min((s.start_time for s in steps if s.start_time), default=None)
        end = max((s.end_time for s in steps if s.end_time), default=None)
        duration = int((end - start).total_seconds() * 1000) if start and end else 0
        in_tok = sum(c.input_tokens for s in steps for c in s.calls if c.call_type == "llm")
        out_tok = sum(c.output_tokens for s in steps for c in s.calls if c.call_type == "llm")
        verdict, retry = None, 0
        for s in steps:  # 取最后一条 verifier Step 的判定
            if s.step_type == "verifier":
                out = s.output or {}
                verdict = out.get("verification_result")
                retry = out.get("rewrite_count", retry)
        return {"duration_ms": duration, "total_input_tokens": in_tok,
                "total_output_tokens": out_tok, "verdict": verdict, "retry_count": retry}

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