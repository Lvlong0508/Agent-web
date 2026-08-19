"""重写轮上下文组装测试：剔除被否决旧候选、保留工具结果、标记重写指令"""

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.services.agent.context.agent import HISTORY_REFERENCE_MARKER
from app.services.agent.capabilities.verifier.context.rewrite import (
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


def test_build_rewrite_messages_excludes_history_reference_block():
    """重写轮定位本轮用户问题时必须排除历史参考块（name=history_reference）。
    兜底形态：build_agent_messages 在历史末条非 user 时无当前问题，消息只剩
    [System, 历史参考块]，旧逻辑会把折叠历史误当成本轮问题，重写轮将失去
    真正的问题。排除标记后，无当前问题时应只返回 系统提示词 + 重写指令。"""
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(
            content="<user>你好</user>\n<assistant>你好，我是小励</assistant>",
            name=HISTORY_REFERENCE_MARKER,
        ),
    ]
    result = build_rewrite_messages(messages, "金额错误")

    # 历史参考块不进入重写轮消息（无当前问题时它不应被当成本轮问题）
    assert not any(getattr(m, "name", None) == HISTORY_REFERENCE_MARKER for m in result)
    # 无当前问题：只剩 系统提示词 + 重写指令，没有用户消息混入
    assert len(result) == 2
    assert result[0].type == "system"
    assert result[1].name == REWRITE_INSTRUCTION_MARKER
    assert "金额错误" in result[1].content


def test_build_rewrite_messages_keeps_current_with_history_block():
    """正常形态（生产主路径）：历史块与当前问题共存时，重写轮仍能正确定位
    本轮用户问题（历史块在本轮之前，reversed 先遇本轮问题，排除标记是双保险）"""
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(
            content="<user>你好</user>\n<assistant>你好，我是小励</assistant>",
            name=HISTORY_REFERENCE_MARKER,
        ),
        HumanMessage(content="本轮问题：我的账单多少？"),
        AIMessage(content="被否决的旧候选"),
    ]
    result = build_rewrite_messages(messages, "金额错误")

    # 历史块被剔除，本轮问题保留为第一条 human
    assert not any(getattr(m, "name", None) == HISTORY_REFERENCE_MARKER for m in result)
    assert result[1].content == "本轮问题：我的账单多少？"


def test_build_rewrite_messages_rewrite_round_drops_first_round():
    """重写轮已调工具（末条 ToolMessage）且存在首轮被否决候选时：只保留
    [系统 + 本轮用户问题 + 重写轮内工具调用/结果 + 指令]，剔除首轮候选与
    首轮工具轮；否则模型重复调工具、消息链膨胀直至质检输入截断（实测 bug）"""
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content="我昨天到底花没花钱？"),
        AIMessage(
            content="",
            tool_calls=[{
                "name": "list_expenses_by_date",
                "args": {"start_date": "2026-08-16", "end_date": "2026-08-16"},
                "id": "call_1",
                "type": "tool_call",
            }],
        ),
        ToolMessage(content='{"total": 0}', name="list_expenses_by_date", tool_call_id="call_1"),
        AIMessage(content="昨天没有支出"),  # 首轮被否决候选
        AIMessage(
            content="",
            tool_calls=[{
                "name": "list_expenses_by_date",
                "args": {"start_date": "2026-08-16", "end_date": "2026-08-16"},
                "id": "call_2",
                "type": "tool_call",
            }],
        ),
        ToolMessage(content='{"total": 0}', name="list_expenses_by_date", tool_call_id="call_2"),
    ]
    result = build_rewrite_messages(messages, "昨天是否有支出请核实")

    # 首轮被否决候选被剔除（不在任何消息 content 中）
    assert "昨天没有支出" not in [m.content for m in result]
    # 结构 = 系统 + 本轮用户问题 + 重写轮内工具调用 + 重写轮工具结果 + 指令
    assert [type(m) for m in result] == [
        SystemMessage, HumanMessage, AIMessage, ToolMessage, HumanMessage,
    ]
    assert result[1].content == "我昨天到底花没花钱？"
    # 重写轮内的工具调用与结果完整保留（结果不丢，模型有据可依）
    assert result[2].tool_calls[0]["id"] == "call_2"
    assert result[3].tool_call_id == "call_2"
    # 指令自适应：已调工具 -> 基于结果作答、不要求再调；且指令带标记
    assert "不要重复调用工具" in result[4].content
    assert result[4].name == REWRITE_INSTRUCTION_MARKER


def test_build_rewrite_messages_excludes_planner_marker():
    """重写轮应过滤规划 SystemMessage（name=planner），避免过时规划约束重新推理"""
    from app.services.agent.capabilities.planner.node import PLANNER_MARKER

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        SystemMessage(
            content="【执行规划参考】意图：QUERY ...",
            name=PLANNER_MARKER,
        ),
        HumanMessage(content="查一下上周账单"),
        AIMessage(content="被否决的候选"),
    ]
    result = build_rewrite_messages(messages, "金额错误")
    assert not any(getattr(m, "name", None) == PLANNER_MARKER for m in result)
    # 系统提示词仍保留
    assert result[0].type == "system"
    assert SYSTEM_PROMPT in result[0].content
