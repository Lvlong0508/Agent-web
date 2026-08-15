"""verifier 能力：质检判定 + 重写循环"""

from langgraph.graph import END, StateGraph

from app.services.agent.capabilities.core_agent.node_names import (
    CORE_NODE_AGENT,
    CORE_NODE_VERIFIER,
)
from app.services.agent.capabilities.verifier.node import (
    make_verifier_node,
    route_after_verify,
)
from app.services.agent.capability import AgentCapability


class VerifierCapability(AgentCapability):
    """质检能力：判定候选回复是否准确，不准确则回 agent 重写（上限 MAX_VERIFY_RETRIES）"""

    @property
    def name(self) -> str:
        return "verifier"

    def __init__(self, tools: list | None = None):
        self._tools = tools or []

    def state_keys(self) -> dict[str, type]:
        # 质检/重写相关字段（预定义在 AgentState）
        return {
            "rewrite_count": int,
            "verification_feedback": str,
            "verification_result": str,
            "verdict": dict,
            "verdict_input": list,
        }

    def register_nodes(self, builder: StateGraph) -> list[str]:
        builder.add_node(CORE_NODE_VERIFIER, make_verifier_node(self._tools))
        return [CORE_NODE_VERIFIER]

    def connect(self, builder: StateGraph) -> None:
        # verifier 条件边：校验通过/超限走 END，反馈非空（需重写）回 agent 重写
        builder.add_conditional_edges(
            CORE_NODE_VERIFIER,
            route_after_verify,
            {"agent": CORE_NODE_AGENT, END: END},
        )
