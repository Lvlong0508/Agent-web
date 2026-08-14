"""agent 运行全链路记录测试：模型默认值与数据访问层"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.agent_run import AgentRun
from app.repositories.agent_run_repo import AgentRunRepo


def test_agent_run_model_defaults():
    """模型默认值：status=ok、无错误、消息列表为空、自动生成 id"""
    run = AgentRun(conversation_id="c1", user_id="u1", model="ollama")
    assert run.status == "ok"
    assert run.error is None
    assert run.messages == []
    assert run.id  # _id 别名自动生成 uuid


@pytest.mark.asyncio
async def test_agent_run_repo_create():
    """create 把 run 按别名序列化插入集合"""
    db = MagicMock()
    repo = AgentRunRepo(db)
    repo.collection.insert_one = AsyncMock(return_value=None)
    run = AgentRun(conversation_id="c1", user_id="u1", model="ollama")

    result = await repo.create(run)

    assert result is run
    repo.collection.insert_one.assert_awaited_once_with(run.model_dump(by_alias=True))


@pytest.mark.asyncio
async def test_agent_run_repo_list_by_conversation():
    """按 conversation_id 查询并按 created_at 升序返回"""
    db = MagicMock()
    now = datetime.now(timezone.utc)
    repo = AgentRunRepo(db)
    repo.collection.find.return_value.sort.return_value.to_list = AsyncMock(
        return_value=[{
            "_id": "r1", "conversation_id": "c1", "user_id": "u1",
            "model": "ollama", "status": "ok", "error": None,
            "messages": [], "created_at": now,
        }]
    )

    runs = await repo.list_by_conversation("c1")

    assert len(runs) == 1
    assert runs[0].conversation_id == "c1"
    # 查询必须带 conversation_id 过滤并按时间升序（回放顺序）
    repo.collection.find.assert_called_once_with({"conversation_id": "c1"})
    # 断言按创建时间升序排序（保证回放顺序）
    repo.collection.find.return_value.sort.assert_called_once_with("created_at", 1)
