"""首轮上下文组装测试：系统提示词前置（含日期）+ 历史消息按序转换"""

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.services.agent.context.agent import build_agent_messages
from app.services.agent.prompts import build_system_prompt


class FakeMessage:
    """模拟 MongoDB 消息对象（仅含 role/content 字段）"""

    def __init__(self, role, content):
        self.role = role
        self.content = content


def test_build_agent_messages_prepends_system_with_date():
    """系统提示词（含当前日期）必须排在最前，随后是转换后的历史消息"""
    history = [
        FakeMessage(role="user", content="你好"),
        FakeMessage(role="assistant", content="你好，我是小励"),
    ]
    result = build_agent_messages(history, "2026-08-15")

    assert isinstance(result[0], SystemMessage)
    assert result[0].content == build_system_prompt("2026-08-15")
    assert isinstance(result[1], HumanMessage)
    assert result[1].content == "你好"
    assert isinstance(result[2], AIMessage)
    assert result[2].content == "你好，我是小励"


def test_build_agent_messages_empty_history():
    """无历史时只返回系统提示词"""
    result = build_agent_messages([], "2026-08-15")
    assert len(result) == 1
    assert isinstance(result[0], SystemMessage)
