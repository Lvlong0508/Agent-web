"""提示词集中管理模块测试：验证模板拼装与系统提示词内容"""

from app.services.prompts import (
    SYSTEM_PROMPT,
    TITLE_GENERATION_TEMPLATE,
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