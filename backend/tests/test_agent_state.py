"""AgentState 测试：新增 skills_index 字段声明"""

from app.services.agent.capabilities.core_agent.state import AgentState


def test_agent_state_declares_skills_index():
    """AgentState 声明 skills_index 字段（供 planner 读取检索结果），可选类型"""
    assert "skills_index" in AgentState.__annotations__
    # 可选字段：降级/缺省时节点用 state.get 回退空串
    assert AgentState.__annotations__["skills_index"] in (str | None, "str | None")