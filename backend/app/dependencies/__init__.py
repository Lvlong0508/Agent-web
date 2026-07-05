from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.exceptions import UnauthorizedError
from app.utils.security import decode_token

# Bearer Token 提取器（从 Authorization 头取令牌）
bearer_scheme = HTTPBearer()


# 依赖注入函数：解析当前请求的用户 ID
# 用法：user_id: str = Depends(get_current_user_id)
def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> str:
    token = credentials.credentials
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise UnauthorizedError("Invalid access token")
    return payload["sub"]
