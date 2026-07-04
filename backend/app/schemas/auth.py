from datetime import datetime

from pydantic import BaseModel, EmailStr, field_validator


# 注册请求体：用户名 + 密码 + 邮箱，含字段校验
class RegisterRequest(BaseModel):
    username: str
    password: str
    email: EmailStr

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        if len(v) < 3 or len(v) > 50:
            raise ValueError("Username must be between 3 and 50 characters")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 6 or len(v) > 128:
            raise ValueError("Password must be between 6 and 128 characters")
        return v


# 登录请求体
class LoginRequest(BaseModel):
    username: str
    password: str


# 刷新令牌请求体
class RefreshTokenRequest(BaseModel):
    refresh_token: str


# 用户信息响应（抑制密码字段不返回）
class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    created_at: datetime

    model_config = {"from_attributes": True}  # 允许从 ORM 模型转换


# 令牌响应（双令牌模式）
class TokenResponse(BaseModel):
    access_token: str   # 短令牌（30 分钟）
    refresh_token: str  # 刷新令牌（7 天）
    token_type: str = "bearer"
