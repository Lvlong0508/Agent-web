"""planner 动态 few-shot 测试：按 L1 粗判 + 动态选择示例 + 工具名动态替换"""

from app.services.agent.capabilities.planner.few_shots import (
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