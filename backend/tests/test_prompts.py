"""提示词集中管理模块测试：验证模板拼装与系统提示词内容"""

from app.services.prompts import (
    REPLY_ON_VERIFY_FAILED,
    SYSTEM_PROMPT,
    TITLE_GENERATION_TEMPLATE,
    VERIFY_PROMPT,
    build_rewrite_prompt,
    build_title_prompt,
)


def test_build_title_prompt_injects_messages():
    """测试标题提示词模板能拼入对话内容"""
    prompt = build_title_prompt("human: 你好")
    assert "human: 你好" in prompt
    # 模板占位符已被替换，不再残留花括号
    assert "{messages_text}" not in prompt


def test_title_template_mentions_short_title():
    """测试标题模板要求生成简短标题（不超过20字）"""
    assert "不超过20个字" in TITLE_GENERATION_TEMPLATE


def test_system_prompt_defines_role():
    """测试系统提示词包含角色名"小励"并承诺好的体验"""
    assert "小励" in SYSTEM_PROMPT
    assert "好的体验" in SYSTEM_PROMPT


def test_system_prompt_requires_tool_for_non_chat_questions():
    """系统提示词必须约束：非纯聊天问题（查账单/时间等）应先调用工具、
    结合工具结果回答，不得凭记忆或猜测编造数据（用户实测：agent 不调用
    工具就编造"3笔/320元"等幻觉数据，导致质检拦截）"""
    assert "调用相应工具" in SYSTEM_PROMPT
    assert "结合工具结果回答" in SYSTEM_PROMPT
    assert "编造数据" in SYSTEM_PROMPT


def test_verify_prompt_exists_and_instructs():
    """验证提示词存在且包含判定指令"""
    assert "is_accurate" in VERIFY_PROMPT
    assert "工具" in VERIFY_PROMPT


def test_verify_prompt_explicitly_targets_last_assistant():
    """质检提示词必须明确校验对象是最后一条 assistant 回复，避免质检员把
    角色设定/用户消息当成交互对象（用户实测：质检员把"你是小励"当成了对话方）"""
    assert "最后一条" in VERIFY_PROMPT
    assert "assistant" in VERIFY_PROMPT


def test_verify_prompt_correcting_user_is_not_inaccurate():
    """质检提示词必须明确：用户可能陈述错误前提（如"我记了3笔"），
    工具返回数据才是唯一事实依据；回复基于工具数据纠正用户是正确行为，
    不能判为不准确（用户实测：agent 答对6笔仍被连续拦截）"""
    assert "错误前提" in VERIFY_PROMPT
    assert "纠正为6笔" in VERIFY_PROMPT
    assert "唯一事实依据" in VERIFY_PROMPT
    assert "不算不准确" in VERIFY_PROMPT


def test_rewrite_prompt_tells_agent_to_reorganize():
    """重写轮指令必须重置前提（回答已被清空）、声明质检员身份、禁止对质检员道歉，
    否则 agent 会暴露"上一条回复未通过校验"这类过程性话术或输出道歉（实测出现"非常抱歉"）"""
    prompt = build_rewrite_prompt("金额错误")
    # 重置前提：清空回答，让 agent 全新开始，不纠结之前的错误
    assert "已被我清空" in prompt
    # 声明质检员身份与中间人角色，防止 agent 把质检员当用户
    assert "质检员" in prompt
    assert "你和用户之间" in prompt
    # 硬性禁令：不得对质检员道歉（可对用户道歉）、不提及质检过程
    assert "不要对质检员我道歉" in prompt
    assert "可以对用户道歉" in prompt
    assert "未通过" not in prompt
    # 反馈正确注入
    assert "金额错误" in prompt


def test_reply_on_verify_failed_is_fixed_message():
    """验证失败超限后返回固定文案"""
    assert REPLY_ON_VERIFY_FAILED == "小励出现了点问题，请稍后再尝试吧"