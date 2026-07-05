from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.auth import (
    RegisterRequest,
    LoginRequest,
    RefreshTokenRequest,
    UserResponse,
    TokenResponse,
)
from app.services.auth_service import AuthService
from app.dependencies import get_current_user_id

# 认证模块路由，统一前缀 /auth
router = APIRouter(prefix="/auth", tags=["auth"])


# POST /auth/register - 用户注册
@router.post("/register", response_model=UserResponse, status_code=201)
async def register(body: RegisterRequest, session: AsyncSession = Depends(get_db)):
    service = AuthService(session)
    return await service.register(body.username, body.email, body.password)


# POST /auth/login - 用户登录，返回 JWT 令牌
@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, session: AsyncSession = Depends(get_db)):
    service = AuthService(session)
    return await service.login(body.username, body.password)


# POST /auth/refresh - 用刷新令牌换取新令牌
@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshTokenRequest, session: AsyncSession = Depends(get_db)):
    service = AuthService(session)
    return await service.refresh(body.refresh_token)


# GET /auth/me - 获取当前登录用户信息（需 Bearer Token）
@router.get("/me", response_model=UserResponse)
async def get_me(
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db),
):
    service = AuthService(session)
    return await service.get_current_user(user_id)
