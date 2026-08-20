"""agent_runs API 测试：schema 映射与路由行为"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.middleware.mongodb import get_db
from app.main import app
from app.models.agent_run import AgentRun
from app.schemas.agent_run import (
    AgentRunDeleteRequest,
    AgentRunDeleteResponse,
    AgentRunListResponse,
    AgentRunResponse,
)


def test_agent_run_response_maps_id_not__id():
    """AgentRunResponse 从 AgentRun 构造：字段输出 id 而非 _id（前端与其他 API 一致）"""
    now = datetime.now(timezone.utc)
    run = AgentRun(
        id="r1",
        conversation_id="c1",
        user_id="u1",
        model="ollama",
        status="ok",
        messages=[{"role": "user", "content": "你好"}],
        trace_id="t1",
        created_at=now,
    )
    resp = AgentRunResponse.model_validate(run)
    assert resp.id == "r1"
    assert resp.conversation_id == "c1"
    assert resp.status == "ok"
    assert resp.messages == [{"role": "user", "content": "你好"}]
    assert resp.created_at == now


def test_agent_run_list_response_aggregates():
    """分页响应：直接聚合 items/total/page/page_size/total_pages"""
    now = datetime.now(timezone.utc)
    run = AgentRun(id="r1", conversation_id="c1", user_id="u1", model="ollama")
    resp = AgentRunListResponse(
        items=[AgentRunResponse.model_validate(run)],
        total=1,
        page=1,
        page_size=20,
        total_pages=1,
    )
    assert resp.items[0].id == "r1"
    assert resp.total == 1
    assert resp.total_pages == 1


def test_agent_run_delete_models():
    """删除请求/响应模型：run_ids 列表、deleted 数量"""
    req = AgentRunDeleteRequest(run_ids=["r1", "r2"])
    assert req.run_ids == ["r1", "r2"]
    resp = AgentRunDeleteResponse(deleted=2)
    assert resp.deleted == 2


@pytest.fixture
def client():
    """TestClient：不用 with 上下文，避免触发 lifespan 连接 MongoDB/建表"""
    return TestClient(app)


@pytest.fixture
def auth_headers():
    """运行记录 API 需要 X-User-Id 头"""
    return {"X-User-Id": "anonymous"}


def test_list_agent_runs_returns_paged(client, auth_headers):
    """GET /agent-runs：返回分页结构，items 映射为 id 字段，page/page_size 透传"""
    now = datetime.now(timezone.utc)
    fake_page = MagicMock()
    fake_page.items = [AgentRun(id="r1", conversation_id="c1", user_id="u1",
                                model="ollama", created_at=now)]
    fake_page.total = 1
    fake_page.page = 2
    fake_page.page_size = 5
    fake_page.total_pages = 1

    app.dependency_overrides[get_db] = lambda: MagicMock()
    with patch("app.api.v1.agent_runs.AgentRunService") as MockService:
        MockService.return_value.list = AsyncMock(return_value=fake_page)
        resp = client.get("/agent-runs?page=2&page_size=5", headers=auth_headers)
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["page"] == 2
    assert body["page_size"] == 5
    assert body["total"] == 1
    assert body["items"][0]["id"] == "r1"
    assert "_id" not in body["items"][0]
    MockService.return_value.list.assert_awaited_once_with(page=2, page_size=5)


def test_delete_agent_runs_returns_deleted(client, auth_headers):
    """DELETE /agent-runs：透传 run_ids，返回 deleted 数量"""
    app.dependency_overrides[get_db] = lambda: MagicMock()
    with patch("app.api.v1.agent_runs.AgentRunService") as MockService:
        MockService.return_value.delete_many = AsyncMock(return_value=2)
        # 本环境 Starlette 1.3.1 的 TestClient.delete 不转发 json 参数，
        # 改走 request("DELETE", ...) 携带请求体，语义不变
        resp = client.request(
            "DELETE",
            "/agent-runs",
            headers=auth_headers,
            json={"run_ids": ["r1", "r2"]},
        )
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json() == {"deleted": 2}
    MockService.return_value.delete_many.assert_awaited_once_with(["r1", "r2"])


def test_agent_runs_requires_user_header(client):
    """不带 X-User-Id 头返回 400（与现有 API 一致）"""
    app.dependency_overrides[get_db] = lambda: None
    try:
        resp = client.get("/agent-runs")
        assert resp.status_code == 400
    finally:
        app.dependency_overrides.clear()
