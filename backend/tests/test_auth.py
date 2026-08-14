"""认证模块测试：引导接口、依赖校验与 contextvar 注入/复位"""

import asyncio

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.auth import current_user_id, get_current_user_id
from app.config.settings import settings
from app.main import app


@pytest.fixture
def client():
    """TestClient：不用 with 上下文，避免触发 lifespan 连接 MongoDB/建表"""
    return TestClient(app)


def test_guest_returns_fixed_user_id(client):
    """引导接口返回硬编码 user_id，前端据此携带 X-User-Id"""
    resp = client.get("/auth/guest")
    assert resp.status_code == 200
    assert resp.json() == {"user_id": settings.DEFAULT_USER_ID}


def test_get_current_user_id_missing_header():
    """缺失 X-User-Id 时抛 400"""
    async def _run():
        gen = get_current_user_id(None)
        with pytest.raises(HTTPException) as exc:
            await gen.__anext__()
        assert exc.value.status_code == 400
    asyncio.run(_run())


def test_get_current_user_id_sets_and_resets():
    """依赖写入 contextvar，结束后复位为 None"""
    async def _run():
        gen = get_current_user_id("user-abc")
        assert await gen.__anext__() == "user-abc"
        assert current_user_id.get() == "user-abc"
        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()
        assert current_user_id.get() is None
    asyncio.run(_run())


def test_chat_api_requires_user_header(client):
    """聊天 API 不带 X-User-Id 时返回 400（API 层强制）"""
    from app.middleware.mongodb import get_db

    # 覆盖 MongoDB 依赖为无操作，避免解析依赖时去连接数据库
    app.dependency_overrides[get_db] = lambda: None
    try:
        resp = client.post("/chat/conversations")
        assert resp.status_code == 400
    finally:
        app.dependency_overrides.clear()


def test_chat_api_with_user_header_succeeds(client):
    """带 X-User-Id 走完整 HTTP 请求：contextvar 注入必须生效。

    回归保护：同步生成器依赖会被 FastAPI 放到线程池执行，set 和 reset
    可能在不同线程（不同 Context），导致 reset(token) 抛
    'Token was created in a different Context'，且 endpoint 读到的
    contextvar 是主协程的 None（抛 RuntimeError: user_id 未注入）。
    必须用 async 生成器依赖，让 set/reset 在请求协程的同一 Context 中执行。
    """
    from unittest.mock import AsyncMock, MagicMock

    from app.middleware.mongodb import get_db

    # 假 db：ChatService 用它构造 ConversationRepo/MessageRepo/AgentRunRepo。
    # 关键是把 conversations 集合的 insert_one 配成 AsyncMock（可 await），
    # 让 create 真正走通，从而验证 contextvar 注入 + 复位全链路。
    fake_db = MagicMock()
    fake_db.__getitem__.return_value = AsyncMock()
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        # 正常请求头必须成功创建对话（不会抛 user_id 未注入或 reset 报错）
        resp = client.post(
            "/chat/conversations",
            headers={"X-User-Id": "user-http"},
        )
        assert resp.status_code == 201
        # 请求结束后 contextvar 必须复位，不能泄漏
        assert current_user_id.get() is None
    finally:
        app.dependency_overrides.clear()