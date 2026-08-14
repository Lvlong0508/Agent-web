from contextvars import ContextVar

from fastapi import Header, HTTPException

# 当前请求用户的上下文变量（Python 版 ThreadLocal，async 安全）。
# 默认 None：尚未注入。service/工具通过它读到本次请求的用户身份。
current_user_id: ContextVar[str | None] = ContextVar("current_user_id", default=None)


def get_current_user_id(x_user_id: str | None = Header(default=None)) -> str:
    """FastAPI 依赖：从 X-User-Id 请求头读取用户并写入 contextvar。

    必须用 Header(default=None) 注解，FastAPI 才会把它当请求头解析；
    否则默认当作查询参数，读不到用户身份。
    缺失时抛 400；存在时 set 进 contextvar，yield 后由 finally 复位
    （等价于 Java ThreadLocal 的 finally remove），保证不泄漏到其他请求。
    """
    if not x_user_id:
        raise HTTPException(status_code=400, detail="X-User-Id header required")
    token = current_user_id.set(x_user_id)
    try:
        yield x_user_id
    finally:
        current_user_id.reset(token)


def get_current_user_id_or_raise() -> str:
    """给 service/工具层读取当前用户 ID。

    返回 None 说明代码路径漏了 get_current_user_id 依赖（程序 bug），
    直接抛错而非静默回退，保持"缺失即报错"的严格性。
    """
    value = current_user_id.get()
    if value is None:
        raise RuntimeError("user_id 未注入：请求上下文缺失")
    return value