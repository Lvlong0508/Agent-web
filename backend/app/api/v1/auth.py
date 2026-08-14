"""用户引导接口：分发 user_id 给前端。

当前是单用户模式，固定返回 settings.DEFAULT_USER_ID（"anonymous"）；
以后接入登录模块时，只替换本函数的返回逻辑（从 token 解析真实用户），
其余代码（service/repo）零改动，隔离架构保持不变。
"""

from fastapi import APIRouter

from app.config.settings import settings

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/guest")
async def guest() -> dict:
    """返回后端分发的用户 ID，前端启动时调用并存 localStorage"""
    return {"user_id": settings.DEFAULT_USER_ID}
