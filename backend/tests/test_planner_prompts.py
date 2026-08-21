"""planner prompt 构建测试：模板稳定 + 动态段注入"""

from langchain_core.messages import HumanMessage, SystemMessage

from app.services.agent.context import (
    build_planner_messages,
    format_plan_system_message,
)
from app.services.agent.context.planner import build_planner_prompt
from app.services.agent.capabilities.planner.schema import PlannerOutput
from app.services.agent.prompts import PLANNER_TEMPLATE
from app.services.agent.prompts.planner import FEW_SHOT_LIBRARY


class _FakeTool:
    def __init__(self, name, description):
        self.name = name
        self.description = description


def test_build_planner_prompt_contains_sections():
    """prompt 含职责/意图定义/工具清单/输出规则，工具名动态生成"""
    prompt = build_planner_prompt(
        user_input="帮我记一笔午饭35块",
        tools=[_FakeTool("create_expense", "新增一条账单")],
        skills_index="## 可用技能\n- **accounting-expert**：记账分类",
    )
    assert "你是一个记账助手的规划器" in prompt
    assert "RECORD" in prompt          # L1 定义
    assert "create_expense" in prompt  # 动态工具清单
    assert "accounting-expert" in prompt  # 技能摘要
    assert "只输出严格合法的 JSON 对象" in prompt  # 输出规则


def test_build_planner_prompt_skills_empty():
    """无技能时技能段为空（skill_section 不注入）"""
    prompt = build_planner_prompt(
        user_input="你好",
        tools=[],
        skills_index="",  # 空技能索引
    )
    assert "可用技能" not in prompt


def test_build_planner_prompt_tools_empty():
    """无工具时工具清单段为空（prompt 仍完整可用）"""
    prompt = build_planner_prompt(
        user_input="你好",
        tools=[],
        skills_index="",
    )
    # 注意：模板输出规则里提到"当前可用工具清单"（文字引用），
    # 这里断言的是动态清单段标题（"## " 前缀）不出现
    assert "## 当前可用工具清单" not in prompt
    assert "你是一个记账助手的规划器" in prompt


def test_build_planner_prompt_includes_few_shot():
    """prompt 含动态 few-shot 示例（按输入粗判 L1）"""
    prompt = build_planner_prompt(
        user_input="帮我记一笔",
        tools=[_FakeTool("create_expense", "新增一条账单")],
        skills_index="",
    )
    assert "输出示例" in prompt


def test_planner_template_exported_from_prompts_init():
    """PLANNER_TEMPLATE 经 prompts 包 __init__ 导出（编排层经包级导入）"""
    assert "你是一个记账助手的规划器" in PLANNER_TEMPLATE
    assert "RECORD" in PLANNER_TEMPLATE
    assert "{tool_section}" in PLANNER_TEMPLATE
    assert "{skill_section}" in PLANNER_TEMPLATE
    assert "{few_shot_section}" in PLANNER_TEMPLATE


def test_few_shot_library_in_prompts_planner():
    """示例库数据位于 prompts/planner.py（静态素材归 prompts 层）"""
    assert "RECORD" in FEW_SHOT_LIBRARY
    assert "QUERY" in FEW_SHOT_LIBRARY
    assert "STATISTICS" in FEW_SHOT_LIBRARY
    assert "SKILL" in FEW_SHOT_LIBRARY


def test_build_planner_messages_returns_message_list():
    """build_planner_messages 返回 [SystemMessage(提示词), HumanMessage(用户本轮)]"""
    messages = build_planner_messages(
        user_input="帮我记一笔午饭35块",
        tools=[_FakeTool("create_expense", "新增一条账单")],
        skills_index="## 可用技能\n- **accounting-expert**：记账分类",
    )
    assert len(messages) == 2
    assert isinstance(messages[0], SystemMessage)
    assert isinstance(messages[1], HumanMessage)
    assert "你是一个记账助手的规划器" in messages[0].content
    assert messages[1].content == "帮我记一笔午饭35块"


def test_build_planner_messages_prompt_equals_planner_prompt():
    """消息里的 SystemMessage 内容与 build_planner_prompt 输出一致（组装正确）"""
    messages = build_planner_messages(
        user_input="帮我记一笔",
        tools=[_FakeTool("create_expense", "新增一条账单")],
        skills_index="",
    )
    expected = build_planner_prompt(
        "帮我记一笔",
        [_FakeTool("create_expense", "新增一条账单")],
        "",
    )
    assert messages[0].content == expected


def test_format_plan_system_message_output():
    """format_plan_system_message 输出与现 _format_plan_system_message 逐字等价"""
    plan = PlannerOutput(
        intent_l1="QUERY",
        intent_l2="QUERY_BY_DATE",
        goal="查询本周账单",
        plan_steps=[{"step_id": 1, "action": "查询本周账单", "suggested_tools": ["list_expenses_by_date"], "depends_on": []}],
        required_tools=["list_expenses_by_date"],
        required_skills=[],
        confidence=0.9,
    )
    text = format_plan_system_message(plan)
    assert "【执行规划参考】" in text
    assert "QUERY/QUERY_BY_DATE" in text
    assert "查询本周账单" in text
    assert "list_expenses_by_date" in text
    assert "0.9" in text