"""提示词集中管理模块测试：验证模板拼装与系统提示词内容"""

from app.services.prompts import (
    REPLY_ON_VERIFY_FAILED,
    SYSTEM_PROMPT,
    TITLE_GENERATION_TEMPLATE,
    VERIFY_PROMPT,
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


def test_verify_prompt_exists_and_instructs():
    """验证提示词存在且包含判定指令"""
    assert "is_accurate" in VERIFY_PROMPT
    assert "工具" in VERIFY_PROMPT


def test_reply_on_verify_failed_is_fixed_message():
    """验证失败超限后返回固定文案"""
    assert REPLY_ON_VERIFY_FAILED == "小励出现了点问题，请稍后再尝试吧"