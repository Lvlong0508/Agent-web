"""组合根：收集能力 → 校验 → 注册节点 → 汇总工具 → 连线 → compile。

设计要点（规格 v3 第 6.3 节）：
- 能力注册顺序由 capabilities/__init__.py 保证（core_agent 第一位）
- 注册阶段所有异常抛 CapabilityRegistryError，由启动入口捕获打印清晰错误
- 必需能力（is_required=True）注册失败中断启动，可选能力失败跳过并记日志
- 节点异常日志兜底由各能力节点函数内部的 try/except 承担（如 title/verifier 的
  降级逻辑），组合根不越权改写 builder（LangGraph 未暴露节点改写入口）
"""

import logging

from langgraph.graph import StateGraph

from app.services.agent.capabilities import get_capabilities
from app.services.agent.capabilities.core_agent.state import AgentState
from app.services.agent.capability import AgentCapability
from app.services.agent.errors import CapabilityRegistryError

logger = logging.getLogger(__name__)


def _validate_capability_order(capabilities: list[AgentCapability]) -> None:
    """校验 core_agent 必须是第一个能力（它是其他能力的锚点宿主）"""
    if not capabilities:
        raise CapabilityRegistryError("__root__", "能力列表为空")
    if capabilities[0].name != "core_agent":
        raise CapabilityRegistryError(
            capabilities[0].name,
            "core_agent 必须是第一个能力（锚点宿主），请检查 capabilities/__init__.py 注册顺序",
        )


def _validate_state_keys(capabilities: list[AgentCapability], state_cls) -> None:
    """校验每个能力声明的 state_keys 字段已存在于 AgentState 定义中"""
    declared = getattr(state_cls, "__annotations__", {})
    for cap in capabilities:
        for field_name in cap.state_keys():
            if field_name not in declared:
                raise CapabilityRegistryError(
                    cap.name,
                    f"声明了 AgentState 中不存在的字段: {field_name}，"
                    "请先在 capabilities/core_agent/state.py 预定义",
                )


def _collect_tools(capabilities: list[AgentCapability], external_tools: list | None = None) -> list:
    """汇总全部能力的工具贡献与外部工具；检测工具重名（重名抛错）"""
    tools = []
    seen_names: set[str] = set()
    for cap in capabilities:
        for tool in cap.tool_contributions():
            if tool.name in seen_names:
                raise CapabilityRegistryError(cap.name, f"工具重名: {tool.name}")
            seen_names.add(tool.name)
            tools.append(tool)
    for tool in external_tools or []:
        if tool.name in seen_names:
            raise CapabilityRegistryError("__root__", f"外部工具与能力工具重名: {tool.name}")
        seen_names.add(tool.name)
        tools.append(tool)
    return tools


def build_agent_graph(conv_repo, capabilities: list[AgentCapability] | None = None, tools: list | None = None):
    """组合根：按注册顺序构建 agent 图。

    conv_repo：对话仓库
    capabilities：能力列表；缺省时用 capabilities/__init__.py 的 get_capabilities()
    tools：外部注入的工具列表（供汇总）；缺省时从能力 tool_contributions() 汇总

    打破"构造能力需要 tools、汇总 tools 又依赖能力"的循环：缺省构建时外部 tools
    已由调用方（chat_service 经 get_tools()）独立生成，直接注入能力构造器即可；
    能力内部的 tool_contributions() 在最后统一汇总，与外部 tools 合并并做重名校验。
    """
    # 1. 构造能力列表：缺省时从能力注册表构造。get_capabilities 的构造器只持有
    #    工具引用、不注册节点，无副作用，可直接用外部 tools 打破循环
    if capabilities is None:
        capabilities = get_capabilities(conv_repo, list(tools or []))

    # 2. 顺序校验：core_agent 必须第一位（其他能力依赖它的锚点节点）
    _validate_capability_order(capabilities)

    # 3. 校验每个能力声明的 state_keys 字段已预定义在 AgentState 中
    _validate_state_keys(capabilities, AgentState)

    # 4. 构建图，注册节点（必需能力失败中断启动，可选能力失败跳过并记日志）
    builder = StateGraph(AgentState)
    registered_nodes: set[str] = set()
    for cap in capabilities:
        try:
            node_names = cap.register_nodes(builder)
            registered_nodes.update(node_names)
        except Exception as e:
            if cap.is_required:
                raise CapabilityRegistryError(cap.name, f"注册失败（必需能力）: {e}") from e
            logger.error("可选能力 [%s] 注册失败，已跳过: %s", cap.name, e)

    # 5. 连线（此时所有节点已注册，connect 可安全引用；失败同注册策略）
    for cap in capabilities:
        try:
            cap.connect(builder)
        except Exception as e:
            if cap.is_required:
                raise CapabilityRegistryError(cap.name, f"连线失败（必需能力）: {e}") from e
            logger.error("可选能力 [%s] 连线失败，已跳过: %s", cap.name, e)

    # 6. 汇总工具与重名检测（能力贡献 + 外部注入）
    _collect_tools(capabilities, tools)

    # 7. 编译（LangGraph 内部校验边引用节点的存在性，异常时附带缺失节点名）
    return builder.compile()
