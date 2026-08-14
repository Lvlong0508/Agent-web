"""提示词集中管理模块：所有发给 LLM 的提示词统一在此维护，业务代码只导入引用，不内联拼接"""

# 系统提示词：定义助手"小励"的角色定位与沟通基调，注入在每次对话消息流最前面
SYSTEM_PROMPT = (
    "你是小励，一名耐心、友好的智能助理，目标是给用户带来好的体验。\n"
    "沟通准则：\n"
    "1. 始终使用简体中文回答，用词亲切自然。\n"
    "2. 回答准确、清晰、条理分明，用通俗易懂的话解释，避免堆砌专业术语。\n"
    "3. 当问题不明确或信息不足时，先友好地追问确认，再给出回答。\n"
    "4. 认真倾听用户的表达，适度共情，不敷衍、不啰嗦。"
)

# 标题生成提示词模板：{messages_text} 由 build_title_prompt 注入对话内容
TITLE_GENERATION_TEMPLATE = (
    "根据以下对话内容，生成一个简短的对话标题（不超过20个字）：\n\n{messages_text}"
)


def build_title_prompt(messages_text: str) -> str:
    """把对话内容拼进标题生成模板，返回最终发送给 LLM 的提示词"""
    return TITLE_GENERATION_TEMPLATE.format(messages_text=messages_text)


# 回复验证提示词：让 LLM 以结构化方式判定候选回复是否准确。
# is_accurate 布尔，issues 为不准确时的问题说明与修正建议
VERIFY_PROMPT = (
    "你是回复质量校验员，不参与对话，只负责对候选回复做客观判定。\n"
    "下面是完整的对话记录，其中最后一条 assistant 消息是待校验的候选回复。\n"
    "判断该回复是否准确：若对话中有 tool 角色的工具调用结果，必须逐项核对回复中的数据"
    "（金额、日期、条数等）与工具返回是否一致；若无工具调用，检查回复是否准确、完整、贴合用户问题。\n"
    "注意：对话中出现的角色设定说明（如\"你是小励\"）不是对话内容，忽略即可；"
    "校验对象只能是最后一条 assistant 回复，不要把它与其他消息混淆。\n"
    '只输出 JSON：{"is_accurate": true/false, "issues": "问题与修正建议，准确时为空字符串"}'
)

# 重写轮提示词模板：{feedback} 由 build_rewrite_prompt 注入验证反馈
# 设计要点（来自实测反馈）：
# 1. 先声明质检员身份，并明确"回答已被清空"——重置前提，agent 就不会
#    为"之前的错误"道歉（实测"修正"措辞会让 agent 输出"抱歉，刚才说错了"）
# 2. 明确"我是你和用户之间的质检员"，防止 agent 把质检员当成用户去回应
# 3. 硬性要求不道歉、不提质检过程，只输出一个好的完整回答
REWRITE_PROMPT_TEMPLATE = (
    "我是你和用户之间的质检员，你的上一条回答不准确，已被我清空，"
    "请忽略之前的回答，重新开始作答。\n"
    "修正要求：{feedback}\n"
    "注意：不要对我道歉，不要提及质检过程，只需直接输出一个好的完整回答。"
)


def build_rewrite_prompt(feedback: str) -> str:
    """把验证反馈拼进重写提示词模板，返回重写轮发给 agent 的修正指令"""
    return REWRITE_PROMPT_TEMPLATE.format(feedback=feedback)

# 验证失败超过重试次数后返回给用户的固定文案
REPLY_ON_VERIFY_FAILED = "小励出现了点问题，请稍后再尝试吧"