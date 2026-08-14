"""agent 运行全链路记录测试：模型默认值、数据访问层与 chat_stream 落库"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from app.auth import current_user_id
from app.config.settings import settings
from app.models.agent_run import AgentRun
from app.models.conversation import Conversation
from app.repositories.agent_run_repo import AgentRunRepo
from app.services.chat_service import ChatService


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


@pytest.mark.asyncio
async def test_chat_stream_saves_full_trace_without_tools():
    """无工具调用：run 记录含 user + assistant 最终回复，status=ok"""
    token = current_user_id.set("anonymous")
    try:
        conv = Conversation(_id="c1", user_id="anonymous")
        service = ChatService(MagicMock())
        service.agent_run_repo = MagicMock()
        service.agent_run_repo.create = AsyncMock(return_value=None)
        service.conv_repo.get_by_id = AsyncMock(return_value=conv)
        service.msg_repo.list_by_conversation = AsyncMock(return_value=[])
        service.msg_repo.create = AsyncMock(return_value=None)

        final_msg = AIMessage(content="你好，很高兴认识你")
        final_chunk = MagicMock()
        final_chunk.content = "你好，很高兴认识你"
        final_chunk.tool_call_chunks = None

        async def fake_astream(input, **kwargs):
            # 先推一条 agent token（用户端），再推 agent 节点的完整输出（全链路）
            yield ("messages", (final_chunk, {"langgraph_node": "agent"}))
            yield ("updates", {"agent": {"messages": [final_msg]}})

        service.graph = MagicMock()
        service.graph.astream = fake_astream

        async for _ in service.chat_stream("c1", "你好", settings.MODEL_OLLAMA):
            pass

        # 断言落库的 run 记录内容
        run = service.agent_run_repo.create.call_args[0][0]
        assert run.status == "ok"
        assert run.conversation_id == "c1"
        assert run.model == settings.MODEL_OLLAMA
        assert [m["role"] for m in run.messages] == ["user", "assistant"]
        assert run.messages[0] == {"role": "user", "content": "你好"}
        assert run.messages[1]["content"] == "你好，很高兴认识你"
    finally:
        current_user_id.reset(token)
