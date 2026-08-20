"""agent_runs API 测试：schema 映射与路由行为"""

from datetime import datetime, timezone

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
