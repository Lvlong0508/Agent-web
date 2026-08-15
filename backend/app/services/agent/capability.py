"""AgentCapability 抽象接口：能力插件化的最小契约。

设计要点（规格 v3 第 4 节）：
- 接口最小化：只有 4 个方法/属性，学习者可维护
- 每个能力自描述：状态字段、节点、连线、工具
- 不依赖全局服务定位器，依赖通过构造注入
"""

from abc import ABC
from typing import Type

from langchain_core.tools import BaseTool
from langgraph.graph import StateGraph


class AgentCapability(ABC):
    """能力插件基类：新增能力 = 新建目录 + 实现本接口 + 一行注册

    注意：本类可直接实例化（name 提供默认空字符串），便于测试与组合根
    对"空能力"的兜底处理。
    """

    @property
    def name(self) -> str:
        """能力唯一标识（注册表 key），子类必须覆写"""
        return ""

    @property
    def is_required(self) -> bool:
        """是否为必需能力：注册失败时是否应中断启动（core_agent 必须覆写为 True）"""
        return False

    def state_keys(self) -> dict[str, Type]:
        """声明本能力读写的主 State 字段（字段名→类型）。

        组合根校验声明的字段必须已存在于 AgentState 定义中（规格 v3：预定义 State，
        不动态合成），不存在则抛 CapabilityRegistryError。
        """
        return {}

    def register_nodes(self, builder: StateGraph) -> list[str]:
        """注册本能力提供的节点，返回注册的节点名列表。

        组合根用返回值做连线引用校验（connect 引用的节点必须存在）。
        """
        return []

    def connect(self, builder: StateGraph) -> None:
        """连线：引用 core_agent 导出的核心节点名常量（CORE_NODE_AGENT 等）挂接自身。

        组合根在全部 register_nodes 之后统一调用本方法，此时所有节点已注册，
        可安全 add_edge / add_conditional_edges。
        """

    def tool_contributions(self) -> list[BaseTool]:
        """本能力提供的工具列表，组合根汇总后注入 tools 锚点（供主 Agent 调用）"""
        return []
