"""planner 动态 few-shot 测试：按 L1 粗判 + 动态选择示例 + 工具名动态替换"""

from app.services.agent.context.planner import (
    build_few_shot_section,
    quick_l1_classify,
)


def test_quick_l1_classify_record():
    """关键词粗判：'记' → RECORD"""
    assert quick_l1_classify("帮我记一笔，午饭35块") == "RECORD"


def test_quick_l1_classify_query():
    """关键词粗判：'查' → QUERY"""
    assert quick_l1_classify("帮我查一下上个月的账单") == "QUERY"


def test_quick_l1_classify_statistics():
    """关键词粗判：'多少' → STATISTICS"""
    assert quick_l1_classify("本月总共花了多少") == "STATISTICS"


def test_quick_l1_classify_fallback():
    """无法粗判时兜底为 CHITCHAT"""
    assert quick_l1_classify("你好呀") == "CHITCHAT"


def test_build_few_shot_section_returns_examples_for_l1():
    """按粗判 L1 返回 1-2 个示例，工具名动态替换为当前真实工具名"""
    current_tools = ["create_expense", "list_expenses_by_date"]
    section = build_few_shot_section("帮我记一笔午饭", current_tools)
    assert "示例" in section
    assert "create_expense" in section  # 动态替换后的真实工具名
    assert "query_bill" not in section  # 不出现旧示例里的写死名


def test_build_few_shot_section_empty_library_fallback():
    """粗判的 L1 无示例时兜底注入通用示例（不返回空段）"""
    section = build_few_shot_section("你好呀", ["create_expense"])
    assert section  # 非空


def test_replace_placeholder_by_prefix_match():
    """占位符按工具名前缀匹配：modify_tool→update_expense, delete_tool→delete_expense"""
    from app.services.agent.context.planner import _replace_tool_names
    output = {
        "required_tools": ["{query_tool}", "{modify_tool}", "{delete_tool}"],
        "plan_steps": [{"suggested_tools": ["{create_tool}", "{stats_tool}"]}],
    }
    result = _replace_tool_names(
        output,
        ["create_expense", "list_expenses_by_date", "update_expense", "delete_expense", "calculate"],
    )
    assert result["required_tools"] == ["list_expenses_by_date", "update_expense", "delete_expense"]
    assert result["plan_steps"][0]["suggested_tools"] == ["create_expense", "calculate"]


def test_replace_placeholder_missing_tool_empty():
    """占位符对应类别工具不存在时替换为空串（不留假名）"""
    from app.services.agent.context.planner import _replace_tool_names
    output = {"required_tools": ["{modify_tool}"]}
    result = _replace_tool_names(output, ["create_expense"])
    assert result["required_tools"] == [""]