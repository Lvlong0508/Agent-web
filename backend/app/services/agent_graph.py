from typing import Literal

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from app.config.settings import settings
from app.repositories.conversation_repo import ConversationRepo


class AgentState(MessagesState):
    """agent 图的共享状态：消息列表（继承）+ 当前对话 ID"""
    conv_id: str


def create_llm(streaming: bool = True, model: str = "") -> ChatOpenAI:
    """按模型选择名创建对应 LLM：本地 Ollama 或通义千问（DashScope）"""
    # 未指定或未知的选择名统一回退本地 Ollama，保证向后兼容
    if model != settings.MODEL_DASHSCOPE_QWEN:
        return ChatOpenAI(
            model=settings.LLM_MODEL,
            base_url=settings.OLLAMA_BASE_URL + "/v1",
            api_key="ollama",  # Ollama 不校验 API Key，但 ChatOpenAI 需要此参数
            streaming=streaming,
        )
    # 通义千问走 DashScope 的 OpenAI 兼容接口，API Key 从环境变量读取
    return ChatOpenAI(
        model=settings.DASHSCOPE_MODEL,
        base_url=settings.DASHSCOPE_BASE_URL,
        api_key=settings.DASHSCOPE_API_KEY,
        streaming=streaming,
    )


async def _generate_title_if_empty(conv, messages, llm) -> str | None:
    """对话标题为空则调用 LLM 生成并返回新标题，否则返回 None（跳过）"""
    # 已有标题则直接跳过，避免覆盖
    if conv and conv.title:
        return None

    # 把消息拼成文本，交给 LLM 生成简短标题
    messages_text = "\n".join(f"{m.type}: {m.content}" for m in messages)
    title_prompt = (
        f"根据以下对话内容，生成一个简短的对话标题（不超过20个字）：\n\n{messages_text}"
    )
    result = await llm.ainvoke([HumanMessage(content=title_prompt)])
    return result.content.strip().strip('"\'')


def should_continue(state: AgentState) -> Literal["tools", END]:
    """条件边：最后一条消息含工具调用则进 tools 节点，否则结束"""
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tools"
    return END


def build_agent_graph(conv_repo: ConversationRepo):
    """构建 agent 骨架图：generate_title → agent →（条件边）→ tools/END"""

    # 标题生成节点：标题为空则生成并写回数据库
    async def generate_title_node(state: AgentState) -> dict:
        conv = await conv_repo.get_by_id(state["conv_id"])
        try:
            title = await _generate_title_if_empty(
                conv, state["messages"], create_llm(streaming=False)
            )
            if title:
                await conv_repo.update_title(state["conv_id"], title)
        except Exception:
            # 标题生成失败不能阻断主聊天流程：静默跳过，回复仍照常产出
            pass
        return {}

    # agent 节点：把全部消息交给 LLM 生成回复（stream_mode 会自动流式输出 token）
    async def agent_node(state: AgentState) -> dict:
        response = await create_llm().ainvoke(state["messages"])
        return {"messages": [response]}

    graph = StateGraph(AgentState)
    graph.add_node("generate_title", generate_title_node)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode([]))  # 骨架阶段空工具，将来在此注册工具
    graph.add_edge(START, "generate_title")
    graph.add_edge("generate_title", "agent")
    graph.add_conditional_edges(
        "agent",
        should_continue,
        {"tools": "tools", END: END},
    )
    return graph.compile()
