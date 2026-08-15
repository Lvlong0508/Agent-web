"""首轮上下文组装：把系统提示词（含当前日期）与历史消息拼成发给 agent 的消息列表"""

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.services.agent.prompts import build_system_prompt


def build_agent_messages(history: list, today: str) -> list:
    """把拉取的历史消息（user/assistant 角色）转成 LangChain 消息，前置
    系统提示词（含当前日期），构造 agent 首轮完整上下文。

    history：MongoDB 消息对象列表（含 role/content 字段），按时间顺序；
    today：YYYY-MM-DD 日期字符串，注入系统提示词（agent 据此才知道"今天"
    是哪天，构造日期类工具参数时才不会幻觉成往年，实测用 2023 年查询当月账单）。
    """
    # 系统提示词只注入一次、排在最前；历史消息只存 user/assistant 角色，
    # 因此不会重复添加系统提示词
    messages = [SystemMessage(content=build_system_prompt(today))]
    for m in history:
        if m.role == "user":
            messages.append(HumanMessage(content=m.content))
        elif m.role == "assistant":
            messages.append(AIMessage(content=m.content))
    return messages
