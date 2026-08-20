"""运行记录（agent_runs）管理 API：分页查询与批量删除。

复用 AgentRunService 已封装的 list / delete_many；
运行记录是管理员排障数据（规格 7.1），不做 user_id 强制隔离。
"""

from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.auth import get_current_user_id
from app.middleware.mongodb import get_db
from app.schemas.agent_run import (
    AgentRunDeleteRequest,
    AgentRunDeleteResponse,
    AgentRunListResponse,
    AgentRunResponse,
)
from app.services.agent_run_service import AgentRunService

# 运行记录管理路由，统一前缀 /agent-runs
router = APIRouter(prefix="/agent-runs", tags=["agent-runs"])


# GET /agent-runs?page=1&page_size=20 — 分页查询运行记录（需 X-User-Id 头）
@router.get("", response_model=AgentRunListResponse)
async def list_agent_runs(
    page: int = 1,
    page_size: int = 20,
    db: AsyncIOMotorDatabase = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
):
    service = AgentRunService(db)
    page_obj = await service.list(page=page, page_size=page_size)
    # 把 ODM 模型转成 API 响应：id 映射（不暴露 _id），前端与其余 API 命名一致
    return AgentRunListResponse(
        items=[AgentRunResponse.model_validate(run) for run in page_obj.items],
        total=page_obj.total,
        page=page_obj.page,
        page_size=page_obj.page_size,
        total_pages=page_obj.total_pages,
    )


# DELETE /agent-runs  body: {"run_ids": [...]} — 批量删除运行记录（需 X-User-Id 头）
@router.delete("", response_model=AgentRunDeleteResponse)
async def delete_agent_runs(
    body: AgentRunDeleteRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
):
    service = AgentRunService(db)
    # 不存在的 id 由 Mongo $in 静默跳过，返回实际删除条数
    deleted = await service.delete_many(body.run_ids)
    return AgentRunDeleteResponse(deleted=deleted)