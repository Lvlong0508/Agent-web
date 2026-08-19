"""首轮上下文组装：把系统提示词（含当前日期）与历史消息拼成发给 agent 的消息列表

历史消息（不含本轮）折叠成一条带 name 标记的 HumanMessage 参考块，只保留
最近 HISTORY_WINDOW_SIZE 条（滑动窗口），省 token 并避免长对话稀释模型对
"本轮要回答什么"的注意力；本轮用户问题独立为最后一条 HumanMessage。
"""

from langchain_core.messages import HumanMessage, SystemMessage

from app.services.agent.prompts import build_system_prompt

# 历史参考块的 name 标记：用于在消息流中区分"历史参考"与"本轮用户问题"。
# rewrite/verdict 定位本轮问题时必须排除带此标记的消息（与 REWRITE_INSTRUCTION_MARKER 同理）
HISTORY_REFERENCE_MARKER = "history_reference"
# 滑动窗口：只保留最近 N 条历史消息（不含本轮），超出部分丢弃以省 token
HISTORY_WINDOW_SIZE = 10


def build_agent_messages(history: list, today: str, skills_index: str = "") -> list:
    """把拉取的历史消息（user/assistant 角色）转成 LangChain 消息，前置
    系统提示词（含当前日期与可选技能索引），构造 agent 首轮完整上下文。

    结构：SystemMessage(系统提示词含日期与技能索引) + HumanMessage(name=history_reference,
    折叠的历史) + HumanMessage(本轮用户问题)。本轮问题永远在最后，模型据此
    明确"当前要回答什么"；历史只是参考块。

    history：MongoDB 消息对象列表（含 role/content 字段），按时间顺序，
    最后一条通常为刚保存的本轮用户消息；
    today：YYYY-MM-DD 日期字符串，注入系统提示词（agent 据此才知道"今天"
    是哪天，构造日期类工具参数时才不会幻觉成往年，实测用 2023 年查询当月账单）；
    skills_index：技能目录清单（L0 索引），缺省空串不追加（skill 机制透明）。
    """
    messages = [SystemMessage(content=build_system_prompt(today, skills_index))]
    if not history:
        return messages

    # 摘出本轮用户问题：正常流程下最后一条是刚保存的用户消息。
    # 若最后一条不是 user（异常兜底），则无本轮问题，全部历史折叠为参考块
    current = history[-1]
    rest = history[:-1]
    if current.role != "user":
        rest = history
        current = None

    # 滑动窗口：只保留最近 HISTORY_WINDOW_SIZE 条历史（不含本轮），
    # 更早的丢弃（省 token 的关键）。history 按 created_at 升序传入，
    # 这里取末 N 条即最近的 N 条
    window = rest[-HISTORY_WINDOW_SIZE:]
    if window:
        # 按序拼成 XML 式角色标签块：<user>内容</user>\n<assistant>内容</assistant>...
        # 角色交替信息靠标签保留，模型读块时能理解谁说了什么
        parts = []
        for m in window:
            tag = "user" if m.role == "user" else "assistant"
            parts.append(f"<{tag}>{m.content}</{tag}>")
        messages.append(
            HumanMessage(content="\n".join(parts), name=HISTORY_REFERENCE_MARKER)
        )

    # 本轮用户问题独立成最后一条（无 name 标记，供 rewrite/verdict 定位）
    if current is not None:
        messages.append(HumanMessage(content=current.content))
    return messages
