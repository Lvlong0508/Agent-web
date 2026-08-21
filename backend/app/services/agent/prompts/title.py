"""title（标题生成提示词）：根据对话内容生成简短对话标题"""

# 标题生成提示词模板：{messages_text} 由 build_title_prompt 注入对话内容
TITLE_GENERATION_TEMPLATE = (
    "根据以下对话内容，生成一个简短的对话标题（不超过20个字）：\n\n{messages_text}"
)


def build_title_prompt(messages_text: str) -> str:
    """把对话内容拼进标题生成模板，返回最终发送给 LLM 的提示词"""
    return TITLE_GENERATION_TEMPLATE.format(messages_text=messages_text)