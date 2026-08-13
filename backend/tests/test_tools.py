"""账单工具测试：验证工具封装与注册（无 MySQL 服务时自动跳过真实调用部分）"""

from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.exc import OperationalError

from app.middleware.mysql import Base, SessionLocal, engine
from app.models.expense import Expense
from app.services.agent_graph import build_agent_graph
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
