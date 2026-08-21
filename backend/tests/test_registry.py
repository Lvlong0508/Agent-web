"""组合根测试：能力顺序校验、必需能力中断、可选能力跳过、工具重名、字段校验"""
from unittest.mock import MagicMock

import pytest
from langchain_core.tools import tool

from app.services.agent.capability import AgentCapability
from app.services.agent.registry import CapabilityRegistryError
from app.services.agent.registry import build_agent_graph


class MockRequired(AgentCapability):
    """模拟 core_agent：必需能力"""

    @property
    def name(self):
        return "core_agent"

    @property
    def is_required(self):
        return True

    def register_nodes(self, builder):
        builder.add_node("agent", lambda state: {"messages": []})
        return ["agent"]

    def connect(self, builder):
        # LangGraph compile 要求图必须有入口边（START → 某节点），否则编译失败
        from langgraph.graph import START

        builder.add_edge(START, "agent")


class MockOptional(AgentCapability):
    """模拟可选能力"""

    @property
    def name(self):
        return "optional"

    def register_nodes(self, builder):
        raise RuntimeError("可选能力初始化失败")


class MockBadField(AgentCapability):
    """声明了不存在的 State 字段"""

    @property
    def name(self):
        return "bad_field"

    def state_keys(self):
        return {"not_exists": str}


@tool
def _dummy_tool(x: int = 1) -> str:
    """测试工具"""
    return str(x)


def test_core_agent_must_be_first():
    """core_agent 不在第一位时启动报错"""
    cap = MockOptional()
    with pytest.raises(CapabilityRegistryError):
        build_agent_graph(MagicMock(), capabilities=[cap])


def test_required_capability_failure_interrupts():
    """必需能力注册失败中断启动"""

    class Boom(AgentCapability):
        @property
        def name(self):
            return "core_agent"

        @property
        def is_required(self):
            return True

        def register_nodes(self, builder):
            raise RuntimeError("必需能力崩溃")

    with pytest.raises(CapabilityRegistryError):
        build_agent_graph(MagicMock(), capabilities=[Boom()])


def test_optional_capability_failure_skipped():
    """可选能力注册失败跳过，不影响整体构建"""
    # 需要一个能成功构建的必需能力（core_agent 第一位）
    graph = build_agent_graph(MagicMock(), capabilities=[MockRequired(), MockOptional()])
    assert graph is not None


def test_state_keys_validate_against_predefined_state():
    """能力声明不存在的 State 字段时启动报错"""
    with pytest.raises(CapabilityRegistryError):
        build_agent_graph(MagicMock(), capabilities=[MockRequired(), MockBadField()])


def test_tool_duplicate_name_raises():
    """两个能力贡献同名工具时启动报错"""

    class WithTool(AgentCapability):
        @property
        def name(self):
            return "tool_cap"

        def tool_contributions(self):
            return [_dummy_tool]

    class WithSameTool(AgentCapability):
        @property
        def name(self):
            return "tool_cap2"

        def tool_contributions(self):
            return [_dummy_tool]

    with pytest.raises(CapabilityRegistryError):
        build_agent_graph(
            MagicMock(), capabilities=[MockRequired(), WithTool(), WithSameTool()]
        )
