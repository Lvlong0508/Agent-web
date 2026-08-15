"""title 能力节点：标题为空则调用 LLM 生成并写回数据库"""

from langchain_core.messages import HumanMessage

from app.services.agent.capabilities.core_agent.llm import create_llm
from app.services.agent.events import emit
from app.services.agent.prompts import build_title_prompt


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
