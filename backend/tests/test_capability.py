"""AgentCapability 接口与 CapabilityRegistryError 测试"""
import pytest

from app.services.agent.capability import AgentCapability
from app.services.agent.registry import CapabilityRegistryError


def test_capability_error_carries_capability_name():
    """CapabilityRegistryError 必须携带能力名，便于定位是哪个能力注册失败"""
    err = CapabilityRegistryError("core_agent", "字段冲突")
    assert err.capability == "core_agent"
    assert "core_agent" in str(err)


def test_defaults_of_agent_capability():
    """能力默认值：非必需、无工具、无状态字段声明"""
    cap = AgentCapability()
    assert cap.name == ""          # 未覆写 name 的空能力
    assert cap.is_required is False
    assert cap.state_keys() == {}
    assert cap.tool_contributions() == []
