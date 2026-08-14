"""认证模块：当前承载用户身份上下文（contextvars），未来登录模块的骨架。

对外统一导出身份相关的上下文与依赖，调用方只需 from app.auth import ...，
不必关心内部文件结构；以后登录模块新增的东西也在这里汇出。
"""

from app.auth.deps import (
    current_user_id,
    get_current_user_id,
    get_current_user_id_or_raise,
)

__all__ = ["current_user_id", "get_current_user_id", "get_current_user_id_or_raise"]
