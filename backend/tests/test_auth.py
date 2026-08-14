"""认证模块测试：引导接口、依赖校验与 contextvar 注入/复位"""

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
    gen = get_current_user_id(None)
    with pytest.raises(HTTPException) as exc:
        next(gen)
    assert exc.value.status_code == 400


def test_get_current_user_id_sets_and_resets():
    """依赖写入 contextvar，结束后复位为 None"""
    gen = get_current_user_id("user-abc")
    assert next(gen) == "user-abc"
    assert current_user_id.get() == "user-abc"
    with pytest.raises(StopIteration):
        next(gen)
    assert current_user_id.get() is None