from typing import Literal

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from app.config.settings import settings
from app.repositories.conversation_repo import ConversationRepo
from app.services.prompts import build_title_prompt


class AgentState(MessagesState):
    """agent 图的共享状态：消息列表（继承）+ 当前对话 ID + 模型选择名 + 新生成的标题 + 思考开关"""
    conv_id: str
    # 注意：TypedDict 状态不应用类属性默认值，缺省回退逻辑在节点内用 state.get 实现
    model: str
    # 标题节点产出的新标题：必须声明在状态 schema 中，stream_mode="updates"
    # 才会把这个字段随节点输出一起推给调用方（未声明的键会被 LangGraph 过滤）
    generated_title: str
    # 深度思考开关：仅通义千问生效，开启时回复先生成思考过程再回答（更慢但更深入）
    thinking: bool


def create_llm(
    streaming: bool = True,
    model: str = "",
    enable_thinking: bool = True,
    max_tokens: int | None = None,
) -> ChatOpenAI:
    """
    按模型选择名创建对应 LLM：本地 Ollama 或通义千问（DashScope）

    enable_thinking：仅对通义千问生效。qwen3 系列默认开启思考模式，
        请求会先输出大段思考 token 再回答，非流式请求要等全部思考完成才返回
        （实测标题生成耗时十几秒）。关闭后响应立即返回，用于"标题要先刷新"
        这类对速度敏感、不需要深度推理的场景。
    max_tokens：限制输出 token 数，防止思考/回答超长拖慢响应。
    """
    # 通义千问：显式匹配选择名
    if model == settings.MODEL_DASHSCOPE_QWEN:
        kwargs = {"streaming": streaming}
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        # 关闭思考时通过 DashScope 兼容模式的请求体参数控制
        if not enable_thinking:
            kwargs["extra_body"] = {"enable_thinking": False}
        return ChatOpenAI(
            model=settings.DASHSCOPE_MODEL,
            base_url=settings.DASHSCOPE_BASE_URL,
            api_key=settings.DASHSCOPE_API_KEY,
            **kwargs,
        )
    # 缺省（未指定）或 Ollama 选择名：回退本地 Ollama，保证向后兼容
    if model == "" or model == settings.MODEL_OLLAMA:
        return ChatOpenAI(
            model=settings.LLM_MODEL,
            base_url=settings.OLLAMA_BASE_URL + "/v1",
            api_key="ollama",  # Ollama 不校验 API Key，但 ChatOpenAI 需要此参数
            streaming=streaming,
        )
    # 非空未知选择名：显式报错，避免前后端常量漂移时静默用错模型
    raise ValueError(f"未知的模型选择名: {model!r}")


async def _generate_title_if_empty(conv, messages, llm) -> str | None:
    """对话标题为空则调用 LLM 生成并返回新标题，否则返回 None（跳过）"""
    # 已有标题则直接跳过，避免覆盖
    if conv and conv.title:
        return None

    # 把消息拼成文本，交给提示词模块生成标题提示词（模板统一维护在 prompts 包）
    messages_text = "\n".join(f"{m.type}: {m.content}" for m in messages)
    title_prompt = build_title_prompt(messages_text)
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

    # 标题生成节点：标题为空则生成并写回数据库，新标题放入状态供上层推送前端
    async def generate_title_node(state: AgentState) -> dict:
        conv = await conv_repo.get_by_id(state["conv_id"])
        title = ""
        try:
            title = await _generate_title_if_empty(
                conv,
                state["messages"],
                create_llm(
                    streaming=False,
                    model=state.get("model") or settings.MODEL_OLLAMA,
                    # 标题生成关闭思考模式并限制输出长度：通义千问开启思考时
                    # 标题请求要等十几秒思考完才返回，会拖到回复之后才刷新；
                    # 关闭后秒回，保证"先刷新标题，再输出内容"
                    enable_thinking=False,
                    max_tokens=100,
                ),
            )
            if title:
                await conv_repo.update_title(state["conv_id"], title)
        except Exception:
            # 标题生成失败不能阻断主聊天流程：静默跳过，回复仍照常产出
            pass
        # 把（可能为空的）标题写回状态：chat_service 用 stream_mode="updates"
        # 监听此字段，一旦非空就通过 SSE 把标题实时推给前端侧边栏
        return {"generated_title": title or ""}

    # agent 节点：把消息流（已含系统提示词）交给 LLM 生成回复
    # （stream_mode 会自动流式输出 token）
    async def agent_node(state: AgentState) -> dict:
        # thinking 开关（缺省 False=关闭）：通义千问开启思考时首 token 要等十几秒，
        # 默认关掉保证回复快速流式输出，用户可在前端按钮手动开启
        response = await create_llm(
            model=state.get("model") or settings.MODEL_OLLAMA,
            enable_thinking=state.get("thinking", False),
        ).ainvoke(state["messages"])
        return {"messages": [response]}

    # 系统提示词由 chat_service 在构造入口状态时前置注入，见 chat_service._run_graph
    # 构造节点node
    graph = StateGraph(AgentState)
    graph.add_node("generate_title", generate_title_node)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode([]))  # 骨架阶段空工具，将来在此注册工具
    # fan-out 并行：标题生成与回复生成互不依赖，同时启动。
    # 若串行（generate_title → agent），标题 LLM 完整生成完才轮到回复流式输出，
    # 首条回复会被标题生成拖慢数秒；并行后回复立即开始流式输出，
    # 标题在后台生成，完成后经 updates 流推送前端侧边栏。
    graph.add_edge(START, "generate_title")
    graph.add_edge(START, "agent")
    # 标题节点是旁路：产出标题即结束，不参与回复链路
    graph.add_edge("generate_title", END)
    graph.add_conditional_edges(
        "agent",
        should_continue,
        {"tools": "tools", END: END},
    )
    return graph.compile()
