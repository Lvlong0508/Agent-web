"""core_agent 能力：主循环核心锚点（agent/tools/verifier 的宿主），必需能力"""

from langgraph.graph import StateGraph
from langgraph.prebuilt import ToolNode

from app.services.agent.capabilities.core_agent.llm import create_llm
from app.services.agent.capabilities.core_agent.node import make_agent_node, should_continue
from app.services.agent.capabilities.core_agent.node_names import (
    CORE_NODE_AGENT,
    CORE_NODE_TOOLS,
    CORE_NODE_VERIFIER,
)
from app.services.agent.capabilities.core_agent.state import AgentState
from app.services.agent.capability import AgentCapability


class CoreAgentCapability(AgentCapability):
    """主循环能力：注册 agent/tools 节点与条件路由，是其他能力的锚点宿主"""

    @property
    def name(self) -> str:
        return "core_agent"

    @property
    def is_required(self) -> bool:
        # 主循环是图的基础，注册失败必须中断启动（规格 7）
        return True

    def __init__(self, conv_repo, tools: list | None = None):
        """注入依赖：对话仓库 + 全部能力汇总后的工具列表（组合根注入）"""
        self._conv_repo = conv_repo
        self._tools = tools or []

    def state_keys(self) -> dict[str, type]:
        # AgentState 定义在 state.py，此处声明公共字段供组合根校验（实际校验
        # 依据是 state.py 预定义，本方法用于文档化 + 未来可能的最小校验）
        return {
            "conv_id": str,
            "user_id": str,
            "model": str,
            "thinking": bool,
            "history_reference": list,
            "trace_id": str,
            "error_info": str,
        }

    def register_nodes(self, builder: StateGraph) -> list[str]:
        builder.add_node(CORE_NODE_AGENT, make_agent_node(self._conv_repo, self._tools))
        builder.add_node(CORE_NODE_TOOLS, ToolNode(self._tools))
        return [CORE_NODE_AGENT, CORE_NODE_TOOLS]

    def connect(self, builder: StateGraph) -> None:
        # 工具执行完必须回到 agent 再跑一轮：agent 拿到工具结果后生成最终回复。
        # 若不连这条边，图在 tools 节点后直接结束，最终回复永远不会产出，
        # 且工具调用轮次里 LLM 输出的中间说明文字会被误收集成回复
        builder.add_edge(CORE_NODE_TOOLS, CORE_NODE_AGENT)
        # agent 条件路由：有工具调用进 tools，无则进 verifier（verifier 节点由
        # verifier 能力注册，存在性校验通过后此处引用）
        builder.add_conditional_edges(
            CORE_NODE_AGENT,
            should_continue,
            {"tools": CORE_NODE_TOOLS, "verifier": CORE_NODE_VERIFIER},
        )
