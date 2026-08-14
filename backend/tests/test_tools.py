"""账单工具测试：验证工具封装与注册（无 MySQL 服务时自动跳过真实调用部分）"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.auth import current_user_id
from app.config.settings import settings
from app.middleware.mysql import Base, SessionLocal, engine
from app.models.expense import Expense
from app.services.agent_graph import Verdict, build_agent_graph
from app.services.chat_service import ChatService
from app.tools import get_tools
from app.tools.expense_tool import build_expense_tools
from app.tools.time_tool import build_time_tools
from tests.conftest import delete_expenses_after, get_max_expense_id

EXPECTED_TOOL_NAMES = {
    "create_expense",
    "get_expense",
    "list_expenses",
    "list_expenses_by_date",
    "update_expense",
    "delete_expense",
    "get_now_time",
}

# 仅账单工厂单独产出的工具名：build_expense_tools 不应包含时间工具
EXPECTED_EXPENSE_TOOL_NAMES = {
    "create_expense",
    "get_expense",
    "list_expenses",
    "list_expenses_by_date",
    "update_expense",
    "delete_expense",
}


def test_build_expense_tools_returns_six_tools():
    """测试工具工厂返回 6 个账单工具（不含时间工具），名称符合预期"""
    tools = build_expense_tools(SessionLocal)
    names = {t.name for t in tools}
    assert names == EXPECTED_EXPENSE_TOOL_NAMES


def test_get_tools_aggregates_all_tools():
    """测试统一注册入口 get_tools 返回全部工具（账单 + 时间）"""
    tools = get_tools(SessionLocal)
    assert {t.name for t in tools} == EXPECTED_TOOL_NAMES


@pytest.mark.asyncio
async def test_get_now_time_tool_returns_valid_time():
    """测试时间工具返回当前时间，格式符合 YYYY-MM-DD HH:MM:SS 且可被 JSON 化"""
    import datetime

    tools = {t.name: t for t in build_time_tools()}
    result = await tools["get_now_time"].ainvoke({})
    # 工具返回的字符串能解析为合法时间（LLM 需要拿到可读的时间文本）
    parsed = datetime.datetime.strptime(result, "%Y-%m-%d %H:%M:%S")
    # 返回的时间与当前系统时间相差应在 1 分钟内（工具确实读的是实时时钟）
    assert abs((datetime.datetime.now() - parsed).total_seconds()) < 60


@pytest.fixture(autouse=True)
def user_context():
    """每个用例注入默认用户身份（工具调用读 contextvar 依赖此值），用例后复位"""
    token = current_user_id.set(settings.DEFAULT_USER_ID)
    yield
    current_user_id.reset(token)


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """真实调用前确保表已创建并记录当前最大 id，结束后只删除本次新增的数据。
    注意：不能用 delete(Expense) 清空整表——测试连的是真实 MySQL，会误删
    用户通过 AI 工具创建的账单；这里只清理 id 大于测试前最大值的行"""
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        max_id_before = await get_max_expense_id()
    except OperationalError:
        pytest.skip("本地 MySQL 不可用，跳过账单工具真实调用测试")
        return
    yield
    await delete_expenses_after(max_id_before)


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
async def test_list_expenses_by_date_tool_filters_by_range():
    """按日期范围工具真实查询：只返回区间内账单，供"上个月支出"类问题使用"""
    tools = {t.name: t for t in build_expense_tools(SessionLocal)}
    # 先造两条不同日期的账单（7月、8月各一条）
    await tools["create_expense"].ainvoke(
        {"category": "food", "amount": 10.0, "date": "2026-07-15", "description": "7月午餐"}
    )
    await tools["create_expense"].ainvoke(
        {"category": "food", "amount": 20.0, "date": "2026-08-14", "description": "8月早餐"}
    )

    result = await tools["list_expenses_by_date"].ainvoke(
        {"start_date": "2026-07-01", "end_date": "2026-07-31"}
    )
    # 7 月区间必须包含刚建的 7月午餐，且不能含 8 月的 8月早餐
    # （区间内可能已有用户历史数据，故不做绝对 total 断言）
    descriptions = [i["description"] for i in result["items"]]
    assert "7月午餐" in descriptions
    assert "8月早餐" not in descriptions
    # 日期都在 7 月范围内
    assert all(i["date"].startswith("2026-07") for i in result["items"])


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
        # verifier 节点会真实调用 _run_verdict（需结构化输出），fake LLM 不支持，
        # patch 成直接返回"准确"，让工具调用链路验证通过后正常结束
        async def fake_run_verdict(llm, messages, history_reference=None, available_tools=None):
            return Verdict(is_accurate=True, issues="")

        with patch("app.services.agent_graph._run_verdict", side_effect=fake_run_verdict):
            with patch("app.services.agent_graph.create_llm", side_effect=fake_create_llm):
                async for _ in graph.astream(
                    {"messages": [HumanMessage(content="记一笔账")], "conv_id": "c1", "user_id": "user-tool", "model": settings.MODEL_OLLAMA},
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
    # 全链路落库在本测试中不关心，mock 掉 create，避免调用真实集合
    service.agent_run_repo = MagicMock()
    service.agent_run_repo.create = AsyncMock(return_value=None)

    token = current_user_id.set("user-loop")
    try:
        events = []
        # verifier 节点会真实调用 _run_verdict（需结构化输出），fake LLM 不支持，
        # patch 成直接返回"准确"，让工具调用链路验证通过后正常结束
        async def fake_run_verdict(llm, messages, history_reference=None, available_tools=None):
            return Verdict(is_accurate=True, issues="")

        with patch("app.services.agent_graph._run_verdict", side_effect=fake_run_verdict):
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
