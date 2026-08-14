"""agent 运行全链路记录测试：模型默认值、数据访问层与 chat_stream 落库"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, ToolMessage

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


@pytest.mark.asyncio
async def test_chat_stream_saves_full_trace_with_tools():
    """含工具调用：run 记录含 user/assistant(tool_calls)/tool/assistant 四类消息"""
    token = current_user_id.set("anonymous")
    try:
        conv = Conversation(_id="c1", user_id="anonymous")
        service = ChatService(MagicMock())
        service.agent_run_repo = MagicMock()
        service.agent_run_repo.create = AsyncMock(return_value=None)
        service.conv_repo.get_by_id = AsyncMock(return_value=conv)
        service.msg_repo.list_by_conversation = AsyncMock(return_value=[])
        service.msg_repo.create = AsyncMock(return_value=None)

        # 模拟一次真实工具调用：agent 决定调用 → 工具执行 → agent 最终回复
        tool_call_msg = AIMessage(
            content="正在查询账单...",
            tool_calls=[{
                "name": "list_expenses",
                "args": {"page": 1, "page_size": 5},
                "id": "call_1",
                "type": "tool_call",
            }],
        )
        tool_result_msg = ToolMessage(
            content='{"items": [], "total": 0, "page": 1, "page_size": 5, "total_pages": 0}',
            name="list_expenses",
            tool_call_id="call_1",
        )
        final_msg = AIMessage(content="你共有 0 条账单")

        async def fake_astream(input, **kwargs):
            # updates 流按执行顺序产出三个节点的完整输出
            yield ("updates", {"agent": {"messages": [tool_call_msg]}})
            yield ("updates", {"tools": {"messages": [tool_result_msg]}})
            yield ("updates", {"agent": {"messages": [final_msg]}})
            # 最终回复轮没有工具调用，token 走 messages 流推给用户端
            final_chunk = MagicMock()
            final_chunk.content = "你共有 0 条账单"
            final_chunk.tool_call_chunks = None
            yield ("messages", (final_chunk, {"langgraph_node": "agent"}))

        service.graph = MagicMock()
        service.graph.astream = fake_astream

        async for _ in service.chat_stream("c1", "查一下账单", settings.MODEL_OLLAMA):
            pass

        run = service.agent_run_repo.create.call_args[0][0]
        # 四类消息按时间顺序完整记录
        assert [m["role"] for m in run.messages] == ["user", "assistant", "tool", "assistant"]
        # 中间 assistant 消息携带工具调用参数
        assert run.messages[1]["tool_calls"][0]["name"] == "list_expenses"
        assert run.messages[1]["tool_calls"][0]["args"] == {"page": 1, "page_size": 5}
        # 工具结果消息带工具名与返回内容
        assert run.messages[2]["name"] == "list_expenses"
        assert "total" in run.messages[2]["content"]
        # 最终回复
        assert run.messages[3]["content"] == "你共有 0 条账单"
    finally:
        current_user_id.reset(token)


@pytest.mark.asyncio
async def test_chat_stream_records_error_run():
    """运行抛异常时：run 记录 status=error 并保存错误信息"""
    token = current_user_id.set("anonymous")
    try:
        conv = Conversation(_id="c1", user_id="anonymous")
        service = ChatService(MagicMock())
        service.agent_run_repo = MagicMock()
        service.agent_run_repo.create = AsyncMock(return_value=None)
        service.conv_repo.get_by_id = AsyncMock(return_value=conv)
        service.msg_repo.list_by_conversation = AsyncMock(return_value=[])
        service.msg_repo.create = AsyncMock(return_value=None)

        async def fake_astream(input, **kwargs):
            # 先产出一条 agent 中间输出，然后模拟模型调用崩溃
            yield ("updates", {"agent": {"messages": [AIMessage(content="正在查询...")]}})
            raise RuntimeError("模型调用超时")

        service.graph = MagicMock()
        service.graph.astream = fake_astream

        with pytest.raises(RuntimeError):
            async for _ in service.chat_stream("c1", "你好", settings.MODEL_OLLAMA):
                pass

        run = service.agent_run_repo.create.call_args[0][0]
        assert run.status == "error"
        assert "模型调用超时" in run.error
        # 已收集到的消息仍保留（用户消息 + 中途 agent 输出）
        assert [m["role"] for m in run.messages] == ["user", "assistant"]
    finally:
        current_user_id.reset(token)
