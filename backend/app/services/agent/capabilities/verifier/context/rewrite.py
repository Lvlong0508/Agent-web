"""重写轮上下文组装：构造重写轮发给 LLM 的消息列表"""

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.services.agent.context.agent import HISTORY_REFERENCE_MARKER
from app.services.agent.prompts import build_rewrite_prompt

# 重写指令的 HumanMessage 标记名：用于在消息流中区分"本轮用户问题"与
# "质检员修正指令"。两条都是 HumanMessage，不带标记就无法定位本轮用户问题
REWRITE_INSTRUCTION_MARKER = "rewrite_instruction"


def build_rewrite_messages(messages, feedback: str) -> list:
    """构造重写轮发给 LLM 的消息列表（方案A，纯函数便于单测）。

    实测 bug：重写轮直接把"完整历史 + 被否决的旧候选回复"喂给 LLM，模型看到
    "这个问题已经回答过了"，最顺的路径是延续旧文本再补一句，而非重新调用工具。
    修复：只保留 系统提示词 + 本轮用户问题 + 重写指令，剔除非本轮/被否决的
    旧消息，迫使模型重新推理——系统提示词的铁律（每轮先调工具）才会生效。

    例外：若重写轮内 agent 已调过工具（最后一条是 ToolMessage），必须保留
    重写轮自己的工具调用与结果（模型据其作答），但首轮被否决候选与首轮工具轮
    仍须剔除——否则模型拿到结果后还会被"必须先重新调用工具"逼着重复调工具，
    消息链逐轮膨胀直至质检输入超长截断降级（实测 bug）。
    """
    # 系统提示词是对话设定，保留；历史工具轮/重写轮/被否决候选一律丢弃
    system_msgs = [m for m in messages if isinstance(m, SystemMessage)]
    # 本轮用户问题：最后一条不带标记的 HumanMessage（带标记的是质检员修正指令或
    # 折叠的历史参考块，两者都不是本轮真实问题，必须一并排除）
    user_question = next(
        (
            m
            for m in reversed(messages)
            if isinstance(m, HumanMessage)
            and getattr(m, "name", None)
            not in (REWRITE_INSTRUCTION_MARKER, HISTORY_REFERENCE_MARKER)
        ),
        None,
    )
    rewrite_messages = list(system_msgs)
    if user_question is not None:
        rewrite_messages.append(user_question)

    # 重写轮内已执行工具：只接续重写轮自己的消息（工具调用/结果），
    # 丢弃首轮被否决候选与首轮工具轮。
    # 边界 = 最后一个"无工具调用的 assistant"（首轮被否决候选）之后；
    # 兜底（测试/无候选的简化形态）则从本轮用户问题之后开始
    has_tool_result = bool(messages) and isinstance(messages[-1], ToolMessage)
    if has_tool_result:
        rewrite_start = 0
        for i, m in enumerate(messages):
            if isinstance(m, AIMessage) and not m.tool_calls:
                rewrite_start = i + 1
        if rewrite_start == 0 and user_question is not None:
            for i, m in enumerate(messages):
                if m is user_question:
                    rewrite_start = i + 1
                    break
        rewrite_messages.extend(messages[rewrite_start:])

    # 重写指令必须带标记：后续重写轮才能从消息流中识别出它，从而定位本轮用户问题。
    # 已调工具时指令自适应为"基于已有结果作答、不重复调工具"（见 build_rewrite_prompt）
    rewrite_messages.append(
        HumanMessage(
            content=build_rewrite_prompt(feedback, has_tool_result),
            name=REWRITE_INSTRUCTION_MARKER,
        )
    )
    return rewrite_messages
