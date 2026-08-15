"""重写轮上下文组装测试：剔除被否决旧候选、保留工具结果、标记重写指令"""

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.services.agent.context.rewrite import (
    REWRITE_INSTRUCTION_MARKER,
    build_rewrite_messages,
)
from app.services.agent.prompts import SYSTEM_PROMPT


def test_build_rewrite_messages_strips_rejected_candidate():
    """方案A：重写轮构造消息必须剔除被否决的旧候选回复（无工具调用的 AIMessage），
    只保留 系统提示词 + 本轮用户问题 + 重写指令。
    否则模型看到旧答案会延续文本而不重新调用工具（实测 bug：质检纠正后仍不调工具）"""
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content="我今天吃了8000块饭，对不？"),
        AIMessage(content="今天没有任何餐饮账单"),  # 被否决的旧候选
    ]
    result = build_rewrite_messages(messages, "金额错误")

    contents = [m.content for m in result]
    assert "今天没有任何餐饮账单" not in contents  # 旧候选被剔除
    assert len(result) == 3
    assert result[0].type == "system"  # 保留系统提示词
    assert result[1].content == "我今天吃了8000块饭，对不？"  # 保留本轮用户问题
    assert result[2].type == "human"
    assert "金额错误" in result[2].content  # 重写指令携带修正意见
    assert result[2].name == REWRITE_INSTRUCTION_MARKER  # 重写指令带标记，便于识别


def test_build_rewrite_messages_keeps_tool_result_round():
    """重写轮已执行工具（末条是 ToolMessage）：保留完整消息（含工具结果）
    只追加重写指令，避免丢失工具结果导致 agent 无据可依"""
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content="我今天吃了8000块饭，对不？"),
        AIMessage(
            content="让我查一下",
            tool_calls=[{"name": "list_expenses", "args": {}, "id": "1", "type": "tool_call"}],
        ),
        ToolMessage(content='{"total": 0}', name="list_expenses", tool_call_id="1"),
    ]
    result = build_rewrite_messages(messages, "金额错误")

    # 完整消息保留，工具结果不得丢失，仅末尾追加重写指令
    assert result[-2] is messages[-1]
    assert isinstance(result[-2], ToolMessage)
    assert isinstance(result[-1], HumanMessage)
    assert result[-1].name == REWRITE_INSTRUCTION_MARKER
    assert "金额错误" in result[-1].content
