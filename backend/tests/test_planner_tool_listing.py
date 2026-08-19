"""planner 动态工具清单测试：从工具列表生成清单文本 + 工具名容错"""

from app.services.agent.capabilities.planner.tool_listing import (
    build_tool_section,
    resolve_tool_name,
    sanitize_required_tools,
)


class _FakeTool:
    """测试替身：模拟 langchain BaseTool 的 name/description 属性"""

    def __init__(self, name, description):
        self.name = name
        self.description = description


def test_build_tool_section_flat():
    """工具清单文本：每项含 name + description，扁平展示（当前 9 个工具）"""
    tools = [
        _FakeTool("create_expense", "新增一条账单"),
        _FakeTool("list_expenses_by_date", "按日期范围查询账单"),
    ]
    text = build_tool_section(tools)
    assert "可用工具清单" in text
    assert "- **create_expense**：新增一条账单" in text
    assert "- **list_expenses_by_date**：按日期范围查询账单" in text


def test_build_tool_section_empty():
    """工具列表为空时不生成清单段（返回空串，planner prompt 兼容）"""
    assert build_tool_section([]) == ""


def test_resolve_tool_name_exact():
    """精确匹配直接返回"""
    assert resolve_tool_name("create_expense", ["create_expense", "list_expenses"]) == "create_expense"


def test_resolve_tool_name_fuzzy_within_edit_distance():
    """编辑距离 ≤2 的近似名自动纠正"""
    assert resolve_tool_name("list_expense", ["create_expense", "list_expenses"]) == "list_expenses"


def test_resolve_tool_name_unmatched_returns_none():
    """无法匹配返回 None（交 agent 自主决策）"""
    assert resolve_tool_name("totally_wrong", ["create_expense"]) is None


def test_sanitize_required_tools_drops_unmatched():
    """清洗工具名列表：非法名丢弃、合法名保留、近似名纠正"""
    cleaned = sanitize_required_tools(
        ["create_expense", "list_expense", "totally_wrong"],
        ["create_expense", "list_expenses"],
    )
    assert "create_expense" in cleaned
    assert "list_expenses" in cleaned
    assert "totally_wrong" not in cleaned