"""首轮上下文组装测试：系统提示词前置（含日期）+ 历史折叠为参考块 + 本轮问题独立"""

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.services.agent.context.agent import (
    HISTORY_REFERENCE_MARKER,
    HISTORY_WINDOW_SIZE,
    build_agent_messages,
)
from app.services.agent.prompts import build_system_prompt


class FakeMessage:
    """模拟 MongoDB 消息对象（仅含 role/content 字段）"""

    def __init__(self, role, content):
        self.role = role
        self.content = content


def test_build_agent_messages_folds_history_and_keeps_current_last():
    """历史（不含本轮）折叠成一条 name=history_reference 的 HumanMessage，
    本轮用户问题独立为最后一条无标记的 HumanMessage"""
    history = [
        FakeMessage(role="user", content="你好"),
        FakeMessage(role="assistant", content="你好，我是小励"),
        FakeMessage(role="user", content="本轮问题：我的账单多少？"),
    ]
    result = build_agent_messages(history, "2026-08-15")

    assert isinstance(result[0], SystemMessage)
    assert result[0].content == build_system_prompt("2026-08-15")
    # 历史折叠为一条带标记的参考块
    assert isinstance(result[1], HumanMessage)
    assert result[1].name == HISTORY_REFERENCE_MARKER
    assert "<user>你好</user>" in result[1].content
    assert "<assistant>你好，我是小励</assistant>" in result[1].content
    # 本轮用户问题独立为最后一条，无 name 标记
    assert len(result) == 3
    assert isinstance(result[2], HumanMessage)
    assert result[2].content == "本轮问题：我的账单多少？"
    assert result[2].name is None


def test_build_agent_messages_window_only_keeps_last_10():
    """历史超过 HISTORY_WINDOW_SIZE 条时，只保留最近 10 条（不含本轮）"""
    history = [FakeMessage(role="user", content=f"第{i}条") for i in range(15)]
    history.append(FakeMessage(role="user", content="本轮问题"))
    result = build_agent_messages(history, "2026-08-15")

    ref_block = result[1]
    assert ref_block.name == HISTORY_REFERENCE_MARKER
    # 折叠块内恰好 HISTORY_WINDOW_SIZE 个 <user> 标签（第 5~14 条，共 10 条）
    assert ref_block.content.count("<user>") == HISTORY_WINDOW_SIZE
    assert "第0条" not in ref_block.content  # 最早的第 0 条被窗口丢弃
    assert "第14条" in ref_block.content     # 最近的旧历史保留
    # 本轮问题独立在最后
    assert result[-1].content == "本轮问题"


def test_build_agent_messages_empty_history():
    """无历史时只返回系统提示词"""
    result = build_agent_messages([], "2026-08-15")
    assert len(result) == 1
    assert isinstance(result[0], SystemMessage)


def test_build_agent_messages_no_current_returns_no_final_human():
    """历史最后一条不是 user（异常兜底）：不产生本轮问题，全部折叠为参考块"""
    history = [FakeMessage(role="user", content="你好"), FakeMessage(role="assistant", content="回复")]
    result = build_agent_messages(history, "2026-08-15")
    # 只有系统提示词 + 参考块，没有最后的本轮问题
    assert len(result) == 2
    assert result[1].name == HISTORY_REFERENCE_MARKER
    assert "<user>你好</user>" in result[1].content
    assert "<assistant>回复</assistant>" in result[1].content
