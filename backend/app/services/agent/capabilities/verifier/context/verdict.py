"""质检员上下文组装与执行：精简对话序列、注入参考信息、调用结构化判定"""

import time

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from pydantic import BaseModel

from app.services.agent.context.agent import HISTORY_REFERENCE_MARKER
from app.services.agent.prompts import VERIFY_PROMPT


class Verdict(BaseModel):
    """验证结论：is_accurate 判定候选回复是否准确，issues 给出问题说明与修正建议"""
    is_accurate: bool
    issues: str


def _call_info_prefix(m: ToolMessage, args: dict | None) -> str:
    """组装"工具名 + 调用参数"前缀；args 为空（该调用无参数）时省略。
    供 _with_call_info（拼进质检员所见 content）与 serialized 落库共用，
    保证两处内容一致"""
    info = f"工具名：{m.name}"
    if args is not None:
        info += f"，调用参数：{args}"
    return info


def _with_call_info(m: ToolMessage, args: dict | None) -> ToolMessage:
    """把工具名与调用参数并进消息内容：OpenAI 格式会丢弃 ToolMessage 的
    name/args 字段，质检员拿不到查询条件就无法判断"条件正确+返回空=无记录"；
    拼进 content 是唯一能传给模型的通道"""
    return ToolMessage(
        content=f"{_call_info_prefix(m, args)}\n返回结果：{m.content}",
        tool_call_id=m.tool_call_id,
        name=m.name,
    )


def build_verdict_input(
    messages,
    history_reference: list | None = None,
    available_tools: list | None = None,
    current_date: str | None = None,
) -> tuple[list, list[dict]]:
    """构造发给质检员的完整输入，返回（精简对话消息, 序列化输入）。

    质检输入由两部分组成：
    - 参考上下文：history_reference（精纯历史，含本轮 user，与传给 agent 的
      记忆一致）。传了它，质检员就能理解基于历史记忆的回复（如历史里用户
      说过自己叫小明）；不传则退化为只保留本轮用户问题。
    - 本轮数据：候选回复（最后一条无 tool_calls 的 assistant）+ 本轮工具结果。
    - 可用工具清单：available_tools 传入工具名列表，质检员据此判断"没有可用
      工具"的说法真伪（清单里有却说没有=说谎），杜绝助手谎称无工具逃避。
    - 当前日期：current_date 传入今天日期（默认取系统当前时间），质检员据此
      判断工具调用参数里的年份是否合理（实测 bug：agent 用 2023 年查询当月
      账单导致查空，质检员因"与工具结果一致"放行了错误结论）。

    精简规则避免质检员被"互相矛盾的旧轮次/重写残稿"干扰（实测 bug：
    质检员判词里已认定"与tool一致、回复准确"，却返回 is_accurate=False）。

    序列化输入供全链路记录（role=input_verdict），便于事后评估质检效果。
    """
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

    # 本轮用户问题：候选回复之前最近的一条 HumanMessage。
    # 注意不能保留所有 HumanMessage——state["messages"] 含多轮历史对话，
    # 历史轮次的用户消息会干扰质检（实测日志 verifier 输入出现多条 HumanMessage）；
    # 带 name=history_reference 标记的折叠历史块同样要排除（它是历史参考，不是
    # 本轮问题，兜底形态下若混入会被质检员误当成当前提问而干扰判定）
    current_user_msg = None
    user_index = -1
    for idx, m in enumerate(dialogue_messages):
        if isinstance(m, HumanMessage) and getattr(m, "name", None) != HISTORY_REFERENCE_MARKER:
            current_user_msg = m
            user_index = idx
        if m is candidate:
            break

    # 本轮工具结果 = 位置在"最近一个被否决候选"之后的 ToolMessage：
    # 重写轮的旧工具结果（首轮被否决周期产生，位于否决候选之前）会干扰质检、
    # 并膨胀质检输入，必须丢弃；无被否决候选（普通单轮）时退化为 user_index
    # 之后（丢弃历史轮次的工具结果）。被否决候选 = 除最终候选外最后一条
    # "无工具调用"的 assistant（首轮已判错、被重写轮替换的旧回复）
    rejected_index = -1
    for idx, m in enumerate(dialogue_messages):
        if isinstance(m, AIMessage) and not m.tool_calls and m is not candidate:
            rejected_index = idx
    tool_lower_bound = rejected_index if rejected_index >= 0 else user_index
    current_tools = [
        m for idx, m in enumerate(dialogue_messages)
        if isinstance(m, ToolMessage) and idx > tool_lower_bound
    ]

    # 参考上下文：有 history_reference 用其完整精纯历史（含本轮 user），
    # 否则退化为只保留本轮用户问题
    if history_reference is not None:
        reference = list(history_reference)
    elif current_user_msg is not None:
        reference = [current_user_msg]
    else:
        reference = []

    # 精简上下文 = 参考上下文 + 本轮工具结果 + 候选回复，顺序按原文保持。
    # 带 tool_calls 的中间轮（"让我查询一下"）与已判错的旧轮次不进入
    reduced = [*reference, *current_tools]
    if candidate is not None:
        reduced.append(candidate)

    # 可用工具清单：作为参考信息注入质检输入（SystemMessage），供质检员判断
    # "没有可用工具"的说法真伪；无工具时跳过（测试/纯 LLM 场景兼容）
    tools_system = None
    if available_tools:
        tools_system = SystemMessage(
            content=f"可用工具清单：{', '.join(available_tools)}"
        )

    # 当前日期参考：作为参考信息注入质检输入（SystemMessage），质检员据此判断
    # 工具参数里的年份是否合理（实测 agent 用 2023 年查询当月账单，若质检员
    # 不知道当前是 2026 年，会误以为查询无误而放行错误结论）。测试可传固定值
    if current_date is None:
        current_date = time.strftime("%Y-%m-%d", time.localtime())
    date_system = SystemMessage(content=f"当前日期：{current_date}")

    # 工具调用参数映射：tool_call_id -> 调用参数。同一工具可能被多次调用且参数不同
    # （如两次 list_expenses_by_date 查不同日期区间），序列化时带上参数才能看出
    # 每条工具结果对应的查询条件，复盘才分得清"同一工具不同结果"的原因
    tool_args_by_id: dict[str, dict] = {}
    for m in dialogue_messages:
        if isinstance(m, AIMessage):
            for tc in m.tool_calls:
                tool_args_by_id[tc["id"]] = tc.get("args")

    # 序列化完整输入（含前置 VERIFY_PROMPT），供全链路记录与日志。
    # tool 消息额外带 name（工具名）与 args（调用参数）：同一工具多次调用、
    # 参数不同导致结果不同，补上这两项才能追溯每条结果由哪次调用产生。
    # 前置参考消息顺序：VERIFY_PROMPT -> 当前日期 -> 可用工具清单
    serialized = [
        {"role": "system", "content": VERIFY_PROMPT},
    ]
    serialized.append({"role": "system", "content": date_system.content})
    if tools_system is not None:
        serialized.append({"role": "system", "content": tools_system.content})
    for m in reduced:
        entry = {"role": getattr(m, "type", "unknown"), "content": m.content}
        if isinstance(m, ToolMessage):
            if m.name:
                entry["name"] = m.name
            args = tool_args_by_id.get(m.tool_call_id)
            if args is not None:
                entry["args"] = args
            # 落库 content 与质检员实际所见保持一致：OpenAI 格式丢弃 ToolMessage
            # 的 name/args 字段，质检员只看 content，序列化副本若用原始 content
            # 复盘时"input_verdict 与真实输入不一致"会误导排查，这里同样注入
            entry["content"] = f"{_call_info_prefix(m, args)}\n返回结果：{m.content}"
        serialized.append(entry)
    # 本轮工具结果注入调用参数：把 name+args 拼进 content（OpenAI 丢弃
    # ToolMessage 的 name/args 字段），质检员才能核对查询条件是否与用户要求一致
    tools_with_info = [
        _with_call_info(m, tool_args_by_id.get(m.tool_call_id))
        for m in current_tools
    ]
    # 精简消息前置参考 SystemMessage（与序列化顺序保持一致）
    reduced = [date_system]
    if tools_system is not None:
        reduced.append(tools_system)
    reduced.extend([*reference, *tools_with_info])
    if candidate is not None:
        reduced.append(candidate)
    return reduced, serialized


async def run_verdict(
    llm,
    messages,
    history_reference: list | None = None,
    available_tools: list | None = None,
    current_date: str | None = None,
) -> Verdict:
    """调用结构化输出 LLM，基于"参考历史 + 本轮数据"得到验证结论。

    参考历史与传给 agent 的记忆一致（精纯 user/assistant），让质检员能理解
    基于记忆的回复；本轮数据只取候选回复与工具结果，丢弃其他历史，避免
    质检员被互相矛盾的多轮回复干扰（实测 bug：质检员判词里已认定"与tool一致、
    回复准确"，却返回 is_accurate=False）。可用工具清单帮助质检员判断"无工具"
    说法真伪；当前日期供质检员识别工具参数年份明显错误的问题。
    """
    structured = llm.with_structured_output(Verdict)
    # 只需精简后的消息序列（reduced）发给质检员；序列化版本由 node.py 侧
    # 单独获取用于全链路落库，此处不消费
    reduced, _ = build_verdict_input(
        messages, history_reference, available_tools, current_date
    )
    return await structured.ainvoke(
        [SystemMessage(content=VERIFY_PROMPT), *reduced]
    )
