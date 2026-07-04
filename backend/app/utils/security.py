from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from app.config.settings import settings
from app.exceptions import AppException

# bcrypt 密码哈希上下文（自动处理 salt 和轮数）
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


# 生成短令牌（用于 API 鉴权，30 分钟过期）
def create_access_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        "iat": now,
        "type": "access",
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


# 生成刷新令牌（用于续期，7 天过期）
def create_refresh_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "exp": now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        "iat": now,
        "type": "refresh",
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


# 解码并验证令牌，失败时抛出统一异常
def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise AppException("Token has expired", "TOKEN_EXPIRED", 401)
    except jwt.InvalidTokenError:
        raise AppException("Invalid token", "INVALID_TOKEN", 401)
