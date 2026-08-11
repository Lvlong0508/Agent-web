import pytest
from unittest.mock import AsyncMock, MagicMock

from app.models.conversation import Conversation
from app.services.chat_service import ChatService


@pytest.fixture
def mock_db():
    """Mock MongoDB 数据库实例"""
    return MagicMock()


@pytest.fixture
def chat_service(mock_db):
    """返回注入 mock db 的 ChatService"""
    return ChatService(mock_db)


@pytest.mark.asyncio
async def test_create_conversation(chat_service):
    """测试创建对话返回正确的格式"""
    # 模拟 ConversationRepo.create 返回一个 Conversation 对象
    chat_service.conv_repo.create = AsyncMock(return_value=Conversation(
        _id="test-id", user_id="user-1", title="",
    ))

    result = await chat_service.create_conversation()

    assert result["id"] == "test-id"
    assert result["title"] == ""
    assert "created_at" in result


@pytest.mark.asyncio
async def test_list_conversations_empty_title(chat_service):
    """测试空标题对话在列表中显示为'新对话'"""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    mock_convs = [
        Conversation(_id="c1", user_id="u1", title="对话1", created_at=now, updated_at=now),
        Conversation(_id="c2", user_id="u1", title="", created_at=now, updated_at=now),
    ]
    chat_service.conv_repo.list_by_user = AsyncMock(return_value=mock_convs)

    result = await chat_service.list_conversations()

    assert len(result) == 2
    assert result[0]["title"] == "对话1"
    assert result[1]["title"] == "新对话"


@pytest.mark.asyncio
async def test_get_messages_unauthorized(chat_service):
    """测试无权访问其他用户的对话"""
    chat_service.conv_repo.get_by_id = AsyncMock(return_value=Conversation(
        _id="c1", user_id="other-user",
    ))

    with pytest.raises(PermissionError):
        await chat_service.get_messages("c1")


@pytest.mark.asyncio
async def test_delete_conversation_unauthorized(chat_service):
    """测试无权删除其他用户的对话"""
    chat_service.conv_repo.get_by_id = AsyncMock(return_value=Conversation(
        _id="c1", user_id="other-user",
    ))

    with pytest.raises(PermissionError):
        await chat_service.delete_conversation("c1")


@pytest.mark.asyncio
async def test_chat_stream_saves_messages(chat_service):
    """测试聊天流通过 agent 图产出 token 并保存 user/assistant 消息"""
    conv = Conversation(_id="c1", user_id="anonymous")
    chat_service.conv_repo.get_by_id = AsyncMock(return_value=conv)
    chat_service.msg_repo.list_by_conversation = AsyncMock(return_value=[])
    chat_service.msg_repo.create = AsyncMock(return_value=None)

    # Mock agent 图：用异步生成器模拟 astream 逐块产出 token
    mock_chunk = MagicMock()
    mock_chunk.content = "你好"
    mock_meta = MagicMock()

    async def fake_astream(*args, **kwargs):
        """假的 graph.astream：产出 (chunk, metadata) 元组"""
        yield (mock_chunk, mock_meta)

    chat_service.graph = MagicMock()
    chat_service.graph.astream = fake_astream

    tokens = []
    async for chunk in chat_service.chat_stream("c1", "hello"):
        tokens.append(chunk)

    # 应收到 SSE token 数据和 [DONE]
    assert any("你好" in t for t in tokens)
    assert any("[DONE]" in t for t in tokens)
    # user 和 assistant 消息各保存一次
    assert chat_service.msg_repo.create.call_count == 2
