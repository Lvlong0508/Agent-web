import logging
from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel

from app.config.settings import settings
from app.repositories.conversation_repo import ConversationRepo
from app.services.prompts import build_rewrite_prompt, build_title_prompt, VERIFY_PROMPT

# 模块级日志器：供节点异常降级等场景记录可诊断信息，便于线上排查
logger = logging.getLogger(__name__)


class AgentState(MessagesState):
    """agent 图的共享状态：消息列表（继承）+ 当前对话 ID + 模型选择名 + 新生成的标题 + 思考开关 + 验证状态"""
    conv_id: str
    # 注意：TypedDict 状态不应用类属性默认值，缺省回退逻辑在节点内用 state.get 实现
    user_id: str  # 当前请求用户 ID：由 chat_service 注入，图节点查询/写入按用户隔离
    model: str
    # 标题节点产出的新标题：必须声明在状态 schema 中，stream_mode="updates"
    # 才会把这个字段随节点输出一起推给调用方（未声明的键会被 LangGraph 过滤）
    generated_title: str
    # 深度思考开关：仅通义千问生效，开启时回复先生成思考过程再回答（更慢但更深入）
    thinking: bool
    # 验证重写计数：verifier 判不准确时累加，超限后返回固定文案（防止无限循环）
    rewrite_count: int
    # 验证反馈：verifier 写给 agent 的修正意见；非空表示候选回复未通过，需重写
    verification_feedback: str
    # 验证结论：verifier 产出的 pass（准确）/ retry（需重写）/ fail（超限）。
    # 必须声明在状态 schema 中，stream_mode="updates" 才会把这个字段推给 chat_service
    # 检测结果（未声明的键会被 LangGraph 静默丢弃）
    verification_result: str
    # 质检员结构化判定（Verdict 的字典）：必须声明才能经 updates 流推给 chat_service，
    # 用于全链路记录追加 role=verdict 条目（未声明的键会被 LangGraph 静默丢弃）
    verdict: dict


# 回复不准确时的最大重写次数：验证->重写->再验证循环的上限，防止无限循环拖慢响应
MAX_VERIFY_RETRIES = 2


class Verdict(BaseModel):
    """验证结论：is_accurate 判定候选回复是否准确，issues 给出问题说明与修正建议"""
    is_accurate: bool
    issues: str


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


def should_continue(state: AgentState) -> Literal["tools", "verifier"]:
    """条件边：最后一条消息含工具调用则进 tools 节点，否则进 verifier 验证"""
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tools"
    return "verifier"


def route_after_verify(state: AgentState) -> Literal["agent", END]:
    """条件边：验证反馈非空（需重写）回 agent，否则（通过或超限）结束"""
    if state.get("verification_feedback"):
        return "agent"
    return END


def _decide_verification(verdict: Verdict, state: AgentState) -> dict:
    """根据验证结论与当前重写次数决定后续状态（纯函数，便于单测）"""
    rewrite_count = state.get("rewrite_count", 0)
    # 准确：清空反馈字段，result=pass，走 END
    if verdict.is_accurate:
        return {
            "verification_feedback": "",
            "verification_result": "pass",
            "rewrite_count": rewrite_count,
        }
    # 不准确但未超限：反馈写入状态、计数+1，result=retry，回 agent 重写
    if rewrite_count < MAX_VERIFY_RETRIES:
        return {
            "verification_feedback": verdict.issues,
            "verification_result": "retry",
            "rewrite_count": rewrite_count + 1,
        }
    # 已达上限：清空反馈、result=fail，走 END（chat_service 检测到 fail 返回固定文案）
    return {
        "verification_feedback": "",
        "verification_result": "fail",
        "rewrite_count": rewrite_count,
    }


async def _run_verdict(llm, messages) -> Verdict:
    """调用结构化输出 LLM，基于"用户问题 + 工具结果 + 候选回复"得到验证结论。

    只取这三类消息，丢弃其他历史：否则质检员会看到互相矛盾的多轮回复
    （如首轮幻觉 320 元、重写轮 70 元），被历史干扰而误判正确回复不准确
    （实测 bug：质检员判词里已认定"与tool一致、回复准确"，却返回 is_accurate=False）。
    """
    structured = llm.with_structured_output(Verdict)
    # 过滤掉角色设定 SystemMessage（如 SYSTEM_PROMPT"你是小励"）：这些不是对话
    # 内容，若保留会与 VERIFY_PROMPT 形成两条 SystemMessage 连排，模型会把角色
    # 设定误当成对话参与者，导致校验对象搞错（实测 bug：把"小励"当成了用户）
    dialogue_messages = [m for m in messages if not isinstance(m, SystemMessage)]

    # 候选回复：最后一条"无工具调用"的 assistant 消息（图结构保证进 verifier
    # 时它是当前待校验的回复；历史中更早的无工具调用回复是已判错的旧轮次，丢弃）
    candidate = None
    for m in reversed(dialogue_messages):
        if isinstance(m, AIMessage) and not m.tool_calls:
            candidate = m
            break

    # 精简上下文：只保留用户问题、工具结果、候选回复三类消息，顺序按原文保持。
    # 带 tool_calls 的中间轮（"让我查询一下"）与已判错的旧轮次都会干扰判定
    reduced = [
        m for m in dialogue_messages
        if isinstance(m, HumanMessage)
        or isinstance(m, ToolMessage)
        or (candidate is not None and m is candidate)
    ]
    # 诊断日志：确认发给质检员的消息序列（SystemMessage 已过滤、旧轮次已丢弃）
    logger.info(
        "verifier 输入消息类型: %s",
        [type(m).__name__ for m in [SystemMessage(content=VERIFY_PROMPT), *reduced]],
    )
    return await structured.ainvoke(
        [SystemMessage(content=VERIFY_PROMPT), *reduced]
    )


def build_agent_graph(conv_repo: ConversationRepo, tools: list | None = None):
    """构建 agent 骨架图：generate_title → agent →（条件边）→ tools/END"""
    tools = tools or []

    # 标题生成节点：标题为空则生成并写回数据库，新标题放入状态供上层推送前端
    async def generate_title_node(state: AgentState) -> dict:
        # get_by_id 带 user_id 参数：按"对话 ID + 归属用户"查询，防越权访问他人对话
        conv = await conv_repo.get_by_id(state["conv_id"], state["user_id"])
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

    # verifier 节点：判定 agent 候选回复是否准确，决定结束/重写/报错
    async def verifier_node(state: AgentState) -> dict:
        llm = create_llm(
            streaming=False,
            model=state.get("model") or settings.MODEL_OLLAMA,
            # 验证不需要深度思考：关闭思考模式让判定快速返回，避免十几秒思考拖慢
            enable_thinking=False,
            # 限制输出长度：质检判定只需短结论（is_accurate + issues），
            # 防止模型在 issues 里写大段自我推敲导致输出过长/截断、判定不稳定
            max_tokens=600,
        )
        try:
            # 诊断日志：记录校验依据——候选回复内容与对话中的工具结果条数，
            # 便于排查"内容正确却被拦"时确认质检员到底核对了什么
            last_msg = state["messages"][-1] if state["messages"] else None
            tool_msgs = [m for m in state["messages"] if m.type == "tool"]
            logger.info(
                "verifier 校验: rewrite_count=%s 候选=%r 工具结果数=%s",
                state.get("rewrite_count", 0),
                getattr(last_msg, "content", "")[:200],
                len(tool_msgs),
            )
            verdict = await _run_verdict(llm, state["messages"])
            logger.info("verifier 判定: is_accurate=%s issues=%r", verdict.is_accurate, verdict.issues)
        except Exception as e:
            # 验证器调用失败（网络异常/模型不支持结构化输出等）不能拖垮主流程：
            # 与标题节点"失败静默跳过"同理，降级为通过（接受候选回复），
            # 保证用户仍能拿到 agent 已产出的合格回复
            logger.warning("验证节点调用失败，降级为通过：%s", e)
            return {
                "verification_feedback": "",
                "verification_result": "pass",
                "rewrite_count": state.get("rewrite_count", 0),
                # 降级时无真实判定，用占位 verdict 保持链路记录字段一致
                "verdict": {"is_accurate": True, "issues": f"验证器调用失败，降级通过：{e}"},
            }
        decision = _decide_verification(verdict, state)
        # 把质检员的结构化判定一并写入状态，供上层全链路记录（role=verdict）
        decision["verdict"] = verdict.model_dump()
        return decision

    # agent 节点：把消息流（已含系统提示词）交给 LLM 生成回复
    # （stream_mode 会自动流式输出 token）
    async def agent_node(state: AgentState) -> dict:
        # 重写轮判断：verifier 未通过时 verification_feedback 非空。
        # 重写轮用非流式 LLM：首轮流式 token 已推给前端，重写轮的 token 若再
        # 逐字推送会造成内容闪烁，故静默生成、验证通过后由 chat_service 推送最终版
        feedback = state.get("verification_feedback", "")
        is_rewrite = bool(feedback)
        llm = create_llm(
            streaming=not is_rewrite,
            model=state.get("model") or settings.MODEL_OLLAMA,
            enable_thinking=state.get("thinking", False),
        )
        # 只在绑定了工具时才 bind_tools：空列表绑定对不支持工具的消息模型会报错
        if tools:
            # bind_tools 把工具 schema 暴露给 LLM，它才能在回复中发起工具调用；
            # 随后条件边 should_continue 检测到 tool_calls 就走 tools 节点执行
            llm = llm.bind_tools(tools)
        messages = state["messages"]
        if is_rewrite:
            # 把验证反馈注入重写指令，agent 据此重新组织语言直接作答。
            # 指令刻意不写"你上一条未通过校验"这类过程性说明：写了会让 agent
            # 在回复里道歉解释（实测出现"非常抱歉，刚才的回复确实出现了严重的
            # 错误"），而重写结果是要展示给用户的最终版，话术必须自然衔接
            messages = [
                *messages,
                HumanMessage(content=build_rewrite_prompt(feedback)),
            ]
        response = await llm.ainvoke(messages)
        return {"messages": [response]}

    # 系统提示词由 chat_service 在构造入口状态时前置注入，见 chat_service._run_graph
    # 构造节点node
    graph = StateGraph(AgentState)
    graph.add_node("generate_title", generate_title_node)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(tools))  # 工具执行节点：条件边命中时运行工具
    graph.add_node("verifier", verifier_node)  # 验证节点：校验候选回复是否准确
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
        # 无工具调用时进 verifier 校验，有工具调用时进 tools 执行
        {"tools": "tools", "verifier": "verifier"},
    )
    # 工具执行完必须回到 agent 再跑一轮：agent 拿到工具结果后生成最终回复。
    # 若不连这条边，图在 tools 节点后直接结束，最终回复永远不会产出，
    # 且工具调用轮次里 LLM 输出的中间说明文字（如"正在查询..."）会被误收集成回复。
    graph.add_edge("tools", "agent")
    # verifier 条件边：校验通过/超限走 END，反馈非空（需重写）回 agent 重写
    graph.add_conditional_edges(
        "verifier",
        route_after_verify,
        {"agent": "agent", END: END},
    )
    return graph.compile()
