"""组合根：收集能力 → 校验 → 注册节点 → 连线 → 编译。

设计要点（规格 v3 第 6.3 节）：
- 能力注册顺序由 capabilities/__init__.py 保证（core_agent 第一位）
- 注册阶段所有异常抛 CapabilityRegistryError，由启动入口捕获打印清晰错误
- 必需能力（is_required=True）注册失败中断启动，可选能力失败跳过并记日志
- 节点异常日志兜底由各能力节点函数内部的 try/except 承担（如 title/verifier 的
  降级逻辑），组合根不越权改写 builder（LangGraph 未暴露节点改写入口）

CapabilityRegistryError 定义在本文件：它几乎只被本组合根抛出（register/connect/
校验/编译各路径），与注册流程强相关，故并归此处而非独立 errors.py 文件。
"""

import logging
from typing import Any

from langgraph.graph import StateGraph

from app.services.agent.capabilities import get_capabilities
from app.services.agent.capabilities.core_agent.state import AgentState
from app.services.agent.capability import AgentCapability

logger = logging.getLogger(__name__)


class CapabilityRegistryError(RuntimeError):
    """能力注册错误：携带出问题的能力名，便于定位。

    注册阶段所有能力注册错误（字段冲突/节点缺失/必需能力失败/工具重名）都抛
    本异常，由启动入口统一捕获并打印清晰错误（规格 6.3）。
    """

    def __init__(self, capability: str, message: str):
        self.capability = capability
        super().__init__(f"[能力 {capability}] {message}")


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


def _validate_tool_names(capabilities: list[AgentCapability], external_tools: list | None = None) -> None:
    """仅校验工具名唯一性（能力贡献 + 外部注入），不负责注入。

    工具注入在能力构造时通过外部 tools 完成（见 build_agent_graph 第 1 步），
    此处只做"重名即抛错"的兜底校验，避免未来某能力贡献了工具却因重名被
    静默忽略（规格 6.3：工具重名必须在启动期暴露）。
    """
    seen_names: set[str] = set()
    for cap in capabilities:
        for tool in cap.tool_contributions():
            if tool.name in seen_names:
                raise CapabilityRegistryError(cap.name, f"工具重名: {tool.name}")
            seen_names.add(tool.name)
    for tool in external_tools or []:
        if tool.name in seen_names:
            raise CapabilityRegistryError("__root__", f"外部工具与能力工具重名: {tool.name}")
        seen_names.add(tool.name)


def build_agent_graph(conv_repo, capabilities: list[AgentCapability] | None = None, tools: list | None = None) -> Any:
    """组合根：按注册顺序构建 agent 图。

    conv_repo：对话仓库
    capabilities：能力列表；缺省时用 capabilities/__init__.py 的 get_capabilities()
    tools：外部注入的工具列表（仅用于工具重名校验；实际注入在能力构造时完成）

    打破"构造能力需要 tools、校验 tools 又依赖能力"的循环：缺省构建时外部 tools
    已由调用方（chat_service 经 get_tools()）独立生成，直接注入能力构造器即可；
    能力内部的 tool_contributions() 在此处只做重名校验，不负责工具注入。
    """
    # 1. 构造能力列表：缺省时从能力注册表构造。get_capabilities 的构造器只持有
    #    工具引用、不注册节点，无副作用，可直接用外部 tools 打破循环
    if capabilities is None:
        capabilities = get_capabilities(conv_repo, list(tools or []))

    # 2. 顺序校验：core_agent 必须第一位（其他能力依赖它的锚点节点）
    _validate_capability_order(capabilities)

    # 3. 校验每个能力声明的 state_keys 字段已预定义在 AgentState 中
    _validate_state_keys(capabilities, AgentState)

    # 4. 工具名校验：提前暴露重名，避免图注册到一半才失败（fail fast）
    _validate_tool_names(capabilities, tools)

    # 5. 构建图，注册节点（必需能力失败中断启动，可选能力失败跳过并记日志）
    builder = StateGraph(AgentState)
    for cap in capabilities:
        try:
            cap.register_nodes(builder)
        except Exception as e:
            if cap.is_required:
                raise CapabilityRegistryError(cap.name, f"注册失败（必需能力）: {e}") from e
            logger.error("可选能力 [%s] 注册失败，已跳过: %s", cap.name, e)

    # 6. 连线（此时所有节点已注册，connect 可安全引用；失败同注册策略）
    for cap in capabilities:
        try:
            cap.connect(builder)
        except Exception as e:
            if cap.is_required:
                raise CapabilityRegistryError(cap.name, f"连线失败（必需能力）: {e}") from e
            logger.error("可选能力 [%s] 连线失败，已跳过: %s", cap.name, e)

    # 7. 编译（LangGraph 内部校验边引用节点的存在性）
    try:
        graph = builder.compile()
    except Exception as e:
        # 编译失败（如引用了未注册/被跳过的节点）统一包装为 CapabilityRegistryError，
        # 附带明确原因，避免裸 LangGraph 错误难定位
        raise CapabilityRegistryError("__root__", f"图编译失败: {e}") from e
    return graph
