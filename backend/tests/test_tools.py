"""账单工具测试：验证工具封装与注册（无 MySQL 服务时自动跳过真实调用部分）"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import delete, select
from sqlalchemy.exc import OperationalError

from app.auth import current_user_id
from app.config.settings import settings
from app.middleware.mysql import Base, SessionLocal, engine
from app.models.expense import Expense
from app.services.agent_graph import build_agent_graph
from app.services.chat_service import ChatService
from app.tools import get_tools
from app.tools.expense_tool import build_expense_tools

EXPECTED_TOOL_NAMES = {
    "create_expense",
    "get_expense",
    "list_expenses",
    "update_expense",
    "delete_expense",
}


def test_build_expense_tools_returns_five_tools():
    """测试工具工厂返回 5 个账单工具，名称符合预期"""
    tools = build_expense_tools(SessionLocal)
    names = {t.name for t in tools}
    assert names == EXPECTED_TOOL_NAMES


def test_get_tools_aggregates_all_tools():
    """测试统一注册入口 get_tools 返回全部工具"""
    tools = get_tools(SessionLocal)
    assert {t.name for t in tools} == EXPECTED_TOOL_NAMES


@pytest.fixture(autouse=True)
def user_context():
    """每个用例注入默认用户身份（工具调用读 contextvar 依赖此值），用例后复位"""
    token = current_user_id.set(settings.DEFAULT_USER_ID)
    yield
    current_user_id.reset(token)


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """真实调用前确保表已创建，结束后清空测试数据"""
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except OperationalError:
        pytest.skip("本地 MySQL 不可用，跳过账单工具真实调用测试")
    yield
    async with engine.begin() as conn:
        await conn.execute(delete(Expense))


@pytest.mark.asyncio
async def test_create_expense_tool_creates_record():
    """测试 create_expense 工具真实创建账单并返回可 JSON 化的结果"""
    tools = {t.name: t for t in build_expense_tools(SessionLocal)}
    result = await tools["create_expense"].ainvoke(
        {"category": "food", "amount": 12.5, "date": "2026-08-05", "description": "午饭"}
    )
    # 返回字典可被 LangChain 序列化，含自增 id
    assert result["category"] == "food"
    assert result["amount"] == "12.50"
    assert result["id"] is not None

    # 数据确实落库
    async with SessionLocal() as session:
        row = (
            await session.execute(select(Expense).where(Expense.id == result["id"]))
        ).scalar_one()
    assert row.category == "food"


@pytest.mark.asyncio
async def test_agent_graph_registers_tools_node():
    """测试把工具传入 build_agent_graph 后 tools 节点包含账单工具"""
    conv_repo = MagicMock()
    tools = build_expense_tools(SessionLocal)
    graph = build_agent_graph(conv_repo, tools=tools)
    nodes = list(graph.get_graph().nodes)
    assert "tools" in nodes
    assert "agent" in nodes


class ToolAwareFakeChatModel(GenericFakeChatModel):
    """支持 bind_tools 且保留 tool_calls 的 fake。

    GenericFakeChatModel 的 _stream 只拆 content、丢弃 tool_calls（流式聚合时
    会丢失工具调用）；这里覆写为整条消息作为一个 chunk 输出，保证
    agent 节点收到的消息完整保留 tool_calls，条件边才能路由到 tools 节点。
    """

    def bind_tools(self, tools, **kwargs):
        return self

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        from langchain_core.outputs import ChatGenerationChunk
        from langchain_core.messages import AIMessageChunk

        message = next(self.messages)
        message_ = AIMessage(content=message) if isinstance(message, str) else message
        chunk = ChatGenerationChunk(
            message=AIMessageChunk(
                content=message_.content,
                tool_call_chunks=[
                    {
                        "name": tc["name"],
                        "args": __import__("json").dumps(tc["args"], ensure_ascii=False),
                        "id": tc.get("id", ""),
                        "index": 0,
                        "type": "tool_call_chunk",
                    }
                    for tc in message_.tool_calls
                ],
                id=message_.id,
            )
        )
        if run_manager:
            run_manager.on_llm_new_token(message_.content, chunk=chunk)
        yield chunk


@pytest.mark.asyncio
async def test_contextvar_propagates_into_agent_tools():
    """关键验证：contextvar 在 agent→tools 执行链中传播，工具落库归属当前用户"""
    conv = MagicMock()
    conv.title = "已有标题"
    conv_repo = MagicMock()
    conv_repo.get_by_id = AsyncMock(return_value=conv)
    conv_repo.update_title = AsyncMock(return_value=None)

    tools = build_expense_tools(SessionLocal)
    graph = build_agent_graph(conv_repo, tools=tools)

    # 第一轮：agent 返回带 tool_calls 的消息，触发 tools 节点；第二轮：最终回复。
    # content 给一个占位字符串：GenericFakeChatModel 的流式实现里空 content 不产出
    # 任何 chunk，会触发 "No generations found"；真实模型流式时会产出带 tool_calls
    # 的 chunk，这里用非空 content 模拟流式行为
    tool_call_msg = AIMessage(
        content="正在查询账单...",
        tool_calls=[{
            "name": "create_expense",
            "args": {"category": "food", "amount": 8.8, "date": "2026-08-06", "description": "隔离测试"},
            "id": "call_1",
            "type": "tool_call",
        }],
    )
    final_msg = AIMessage(content="已记账")

    # 每轮 agent 调用都要返回一个带全新迭代器的 fake：GenericFakeChatModel 的
    # 一次 ainvoke 会一次性吃光迭代器，共享迭代器会导致第二轮拿到空流。
    agent_call_count = {"n": 0}

    def fake_create_llm(streaming=True, model="", enable_thinking=True, max_tokens=None):
        if not streaming:
            return GenericFakeChatModel(messages=iter([AIMessage(content='"标题"')]))
        agent_call_count["n"] += 1
        # 第一轮返回带 tool_calls 的消息触发 tools 节点，第二轮返回最终回复结束
        if agent_call_count["n"] == 1:
            return ToolAwareFakeChatModel(messages=iter([tool_call_msg]))
        return ToolAwareFakeChatModel(messages=iter([final_msg]))

    token = current_user_id.set("user-tool")
    try:
        with patch("app.services.agent_graph.create_llm", side_effect=fake_create_llm):
            async for _ in graph.astream(
                {"messages": [HumanMessage(content="记一笔账")], "conv_id": "c1", "model": settings.MODEL_OLLAMA},
                stream_mode="messages",
            ):
                pass
    finally:
        current_user_id.reset(token)

    # 工具落库的账单归属 contextvar 注入的用户
    async with SessionLocal() as session:
        rows = (
            await session.execute(select(Expense).where(Expense.user_id == "user-tool"))
        ).scalars().all()
    assert len(rows) == 1
    assert rows[0].category == "food"


@pytest.mark.asyncio
async def test_agent_tool_loop_returns_final_reply_and_filters_mid_round():
    """回归测试：tools 执行后必须回到 agent 再跑一轮产出最终回复，
    且 chat_stream 不得把工具调用轮的中间说明文字混入流式回复。

    背景：曾存在两个 bug——
    1. 图缺 tools→agent 边，工具执行完直接结束，最终回复永不产出；
    2. chat_stream 收集了工具调用轮的 content（如"正在查询..."），污染回复。
    """
    conv = MagicMock()
    conv.title = "已有标题"
    conv_repo = MagicMock()
    conv_repo.get_by_id = AsyncMock(return_value=conv)
    conv_repo.update_title = AsyncMock(return_value=None)

    tools = build_expense_tools(SessionLocal)
    graph = build_agent_graph(conv_repo, tools=tools)

    msg_repo = MagicMock()
    msg_repo.create = AsyncMock(return_value=None)
    msg_repo.list_by_conversation = AsyncMock(
        return_value=[MagicMock(role="user", content="查一下账单")]
    )

    # 第一轮：agent 决定调用工具（带中间说明文字）；第二轮：基于工具结果的最终回复
    tool_call_msg = AIMessage(
        content="正在查询账单...",  # 中间说明文字，不应进入最终回复
        tool_calls=[{
            "name": "list_expenses",
            "args": {"page": 1, "page_size": 5},
            "id": "call_1",
            "type": "tool_call",
        }],
    )
    final_msg = AIMessage(content="你共有 3 条账单")

    agent_call_count = {"n": 0}

    def fake_create_llm(streaming=True, model="", enable_thinking=True, max_tokens=None):
        if not streaming:
            return GenericFakeChatModel(messages=iter([AIMessage(content='"标题"')]))
        agent_call_count["n"] += 1
        if agent_call_count["n"] == 1:
            return ToolAwareFakeChatModel(messages=iter([tool_call_msg]))
        return ToolAwareFakeChatModel(messages=iter([final_msg]))

    service = ChatService(MagicMock(), graph=graph)
    service.msg_repo = msg_repo
    service.conv_repo = conv_repo

    token = current_user_id.set("user-loop")
    try:
        events = []
        with patch("app.services.agent_graph.create_llm", side_effect=fake_create_llm):
            async for line in service.chat_stream(
                "c1", "查一下账单", settings.MODEL_OLLAMA, thinking=False
            ):
                events.append(line)
    finally:
        current_user_id.reset(token)

    # 1. 最终回复 token 必须被推送（图跑完了 tools → agent 第二轮）
    token_text = "".join(
        line[len("data: "):].rstrip("\n\n") for line in events
        if line.startswith("data: ")
    )
    assert "你共有 3 条账单" in token_text
    # 2. 工具调用轮的中间说明文字不得进入回复流
    assert "正在查询账单" not in token_text
    # 3. 保存的 assistant 内容也必须是干净的最终回复
    saved = msg_repo.create.call_args_list[-1][0][0]
    assert saved.content == "你共有 3 条账单"
