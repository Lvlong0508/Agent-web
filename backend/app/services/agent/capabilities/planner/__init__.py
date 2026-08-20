"""planner 能力：意图识别 + 目标分析 + 路线规划（插在 agent 推理之前）"""

from langgraph.graph import StateGraph

from app.services.agent.capabilities.core_agent.node_names import (
    CORE_NODE_AGENT,
    CORE_NODE_PLANNER,
)
from app.services.agent.capabilities.core_agent.state import AgentState
from app.services.agent.capabilities.planner.node import make_planner_node
from app.services.agent.capability import AgentCapability


class PlannerCapability(AgentCapability):
    """规划能力：在 agent 推理前做意图识别与路线规划，结果注入 agent 上下文"""

    @property
    def name(self) -> str:
        return "planner"

    @property
    def is_required(self) -> bool:
        # 规划节点是主循环结构的一部分（core_agent.connect 引用 CORE_NODE_PLANNER），
        # 注册失败被跳过会导致图编译失败，故注册必需。
        # 注意：注册必需 ≠ 运行必需——节点内 LLM 失败走降级，不影响主流程（spec 3.3）
        return True

    def __init__(self, tools: list | None = None):
        self._tools = tools or []

    def state_keys(self) -> dict[str, type]:
        # 规划相关字段（预定义在 AgentState，本处声明供校验与文档化）
        return {
            "planner_result": dict | None,
            "planner_status": str,
            "planner_reason": str,
            "planner_cost_ms": int,   # 规划耗时（毫秒）：与 AgentState 保持一致，供 updates 流带出
        }

    def register_nodes(self, builder: StateGraph) -> list[str]:
        builder.add_node(CORE_NODE_PLANNER, make_planner_node(self._tools))
        return [CORE_NODE_PLANNER]

    def connect(self, builder: StateGraph) -> None:
        # 规划后进 agent（挂接核心锚点）；START→planner 由 core_agent 认领（主路径入口）
        builder.add_edge(CORE_NODE_PLANNER, CORE_NODE_AGENT)