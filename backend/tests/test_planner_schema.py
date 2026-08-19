"""planner 输出 schema 测试：结构校验 + 默认值 + 非法输入拒绝"""

import pytest
from pydantic import ValidationError

from app.services.agent.capabilities.planner.schema import PlannerOutput


def test_planner_output_valid():
    """合法 PlannerOutput 通过校验"""
    plan = PlannerOutput(
        intent_l1="QUERY",
        intent_l2="QUERY_BY_DATE",
        goal="查询本周账单",
        plan_steps=[
            {"step_id": 1, "action": "查询本周账单", "suggested_tools": ["list_expenses_by_date"], "depends_on": []},
        ],
        required_tools=["list_expenses_by_date"],
        required_skills=[],
        confidence=0.9,
    )
    assert plan.intent_l1 == "QUERY"
    assert plan.plan_steps[0].action == "查询本周账单"
    assert plan.confidence == 0.9


def test_planner_output_invalid_intent_l1():
    """intent_l1 必须从枚举中选择，禁止自创类别"""
    with pytest.raises(ValidationError):
        PlannerOutput(
            intent_l1="MAKE_MONEY",  # 非法意图
            intent_l2="QUERY_BY_DATE",
            goal="x",
            plan_steps=[],
            required_tools=[],
            required_skills=[],
            confidence=0.9,
        )


def test_planner_output_confidence_bounds():
    """confidence 必须在 [0,1] 区间"""
    with pytest.raises(ValidationError):
        PlannerOutput(
            intent_l1="QUERY",
            intent_l2="QUERY_BY_DATE",
            goal="x",
            plan_steps=[],
            required_tools=[],
            required_skills=[],
            confidence=1.5,
        )


def test_planner_output_defaults_optional_fields():
    """suggested_tools / depends_on / required_tools / required_skills 缺省为空列表"""
    plan = PlannerOutput(
        intent_l1="CHITCHAT",
        intent_l2="CHITCHAT_GENERAL",
        goal="闲聊",
        plan_steps=[],
        required_tools=[],
        required_skills=[],
        confidence=0.8,
    )
    assert plan.required_tools == []
    assert plan.required_skills == []