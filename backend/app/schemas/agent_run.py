from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.agent_run import AgentRun


class AgentRunPage(BaseModel):
    """运行记录分页响应：与 ExpensePage 对齐的通用分页结构（items+total+分页信息）"""
    items: list[AgentRun]   # 当前页的运行记录
    total: int              # 满足过滤条件的总条数
    page: int               # 当前页码（从 1 开始）
    page_size: int          # 每页条数
    total_pages: int        # 总页数 = ceil(total / page_size)


class AgentRunResponse(BaseModel):
    """运行记录响应：字段用 id（不用 _id），与其余 API 命名一致。
    从 AgentRun（ODM）构造：from_attributes 允许直接 model_validate(对象)"""
    id: str
    conversation_id: str
    user_id: str
    model: str
    status: str          # "ok" | "error"
    error: str | None
    trace_id: str
    created_at: datetime
    messages: list[dict]  # 全链路消息（兼容字段，旧记录）
    # === 三层结构（spec 2026-08-22）：运行级汇总 + 节点级步骤，向后兼容新增 ===
    duration_ms: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    verdict: str | None = None
    retry_count: int = 0
    steps: list[dict] = []  # TraceStep 的 dict 序列化（前端可渲染节点分组）

    model_config = ConfigDict(from_attributes=True)

    @field_validator("steps", mode="before")
    @classmethod
    def _steps_to_dict(cls, v):
        """把 ODM 里的 TraceStep 对象列表转成 dict（API 层不暴露模型对象）"""
        if v is None:
            return []
        return [s.model_dump() if hasattr(s, "model_dump") else s for s in v]


class AgentRunListResponse(BaseModel):
    """运行记录分页响应（API 层）"""
    items: list[AgentRunResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class AgentRunDeleteRequest(BaseModel):
    """批量删除请求体：run_ids 至少 1 个（空列表由 service 早退返回 0）"""
    run_ids: list[str]


class AgentRunDeleteResponse(BaseModel):
    """批量删除响应：实际删除条数"""
    deleted: int