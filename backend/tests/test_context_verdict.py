"""质检员上下文组装与执行测试：精简对话、注入参考信息、结构化判定"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.services.agent.context.verdict import (
    Verdict,
    build_verdict_input,
    run_verdict,
)
from app.services.agent.prompts import SYSTEM_PROMPT, VERIFY_PROMPT


@pytest.mark.asyncio
async def test_run_verdict_injects_verify_prompt_and_calls_structured_llm():
    """_run_verdict 注入验证提示词并调用结构化输出"""
    mock_llm = MagicMock()
    structured = MagicMock()
    structured.ainvoke = AsyncMock(return_value=Verdict(is_accurate=True, issues=""))
    mock_llm.with_structured_output.return_value = structured

    messages = [HumanMessage(content="hi")]
    result = await run_verdict(mock_llm, messages)

    assert result.is_accurate is True
    # 验证提示词作为 SystemMessage 前置注入
    call_messages = structured.ainvoke.call_args.args[0]
    assert call_messages[0].type == "system"
    assert VERIFY_PROMPT in call_messages[0].content
    # 当前日期参考 SystemMessage 紧随其后
    assert call_messages[1].type == "system"
    assert "当前日期" in call_messages[1].content
    # 原始对话消息保持在提示词与日期参考之后
    assert call_messages[2] == messages[0]


@pytest.mark.asyncio
async def test_run_verdict_filters_system_role_message():
    """_run_verdict 必须过滤掉角色设定 SystemMessage（如 SYSTEM_PROMPT"你是小励"），
    只保留 user/assistant/tool 对话消息交给质检员；否则两条 SystemMessage 连排
    会让模型把角色设定当成对话参与者，导致校验对象搞错（用户实测 bug）"""
    mock_llm = MagicMock()
    structured = MagicMock()
    structured.ainvoke = AsyncMock(return_value=Verdict(is_accurate=True, issues=""))
    mock_llm.with_structured_output.return_value = structured

    # 模拟真实场景：state["messages"] 开头有 chat_service 注入的 SYSTEM_PROMPT
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content="现在几点了？"),
        AIMessage(content="候选回复"),
    ]
    result = await run_verdict(mock_llm, messages)

    assert result.is_accurate is True
    call_messages = structured.ainvoke.call_args.args[0]
    # 除 VERIFY_PROMPT 与当前日期参考外，不再有第三条 SystemMessage（角色设定被过滤）
    system_msgs = [m for m in call_messages if isinstance(m, SystemMessage)]
    assert len(system_msgs) == 2
    assert system_msgs[0].content == VERIFY_PROMPT
    assert "当前日期" in system_msgs[1].content
    # 对话消息完整保留且顺序不变（角色设定被过滤后只留 human/assistant）
    assert [type(m) for m in call_messages[2:]] == [HumanMessage, AIMessage]


@pytest.mark.asyncio
async def test_run_verdict_filters_stale_rounds_keeps_candidate_and_tool():
    """_run_verdict 必须丢弃历史中已判错/重写的旧回复与带工具调用的中间轮，
    只保留：用户消息 + 工具结果 + 最后一条无工具调用的候选回复。
    否则质检员会看到互相矛盾的多轮回复（如首轮幻觉 320 元、重写轮 70 元），
    被历史干扰而误判正确回复不准确（用户实测 bug）"""
    mock_llm = MagicMock()
    structured = MagicMock()
    structured.ainvoke = AsyncMock(return_value=Verdict(is_accurate=True, issues=""))
    mock_llm.with_structured_output.return_value = structured

    # 模拟真实重写场景的消息序列（含首轮幻觉 + 工具调用中间轮 + 工具结果 + 重写候选）
    messages = [
        HumanMessage(content="我这个月一共花了 800 块，是不是？"),
        # 首轮幻觉回复（320 元，错）
        AIMessage(content="我这个月一共花了 320 元"),
        # 重写轮中间轮：先声明再调用工具（带 tool_calls 的 assistant）
        AIMessage(
            content="让我重新核对一下",
            tool_calls=[{"name": "list_expenses", "args": {"page": 1, "page_size": 100}, "id": "1", "type": "tool_call"}],
        ),
        # 工具结果
        ToolMessage(content='{"total": 6, "items": [...]}', name="list_expenses", tool_call_id="1"),
        # 重写轮最终候选（70 元，正确）
        AIMessage(content="我这个月一共花了 70 元"),
    ]
    await run_verdict(mock_llm, messages)

    call_messages = structured.ainvoke.call_args.args[0]
    # 前置 VERIFY_PROMPT 后，其余消息应只剩：当前日期参考 + 用户 + 工具结果 + 候选回复
    remaining = [m for m in call_messages[1:] if not isinstance(m, SystemMessage)]
    # 丢弃了首轮幻觉回复与带工具调用的中间轮
    assert [type(m) for m in remaining] == [HumanMessage, ToolMessage, AIMessage]
    # 候选回复必须是最后一条无工具调用的 assistant（70 元那条）
    assert remaining[-1].content == "我这个月一共花了 70 元"
    assert not any("320 元" in m.content for m in remaining if isinstance(m, AIMessage))


@pytest.mark.asyncio
async def test_run_verdict_keeps_only_current_round_user_message():
    """质检上下文只能包含本轮用户问题，不能混入历史轮次的用户消息。
    否则质检员会被上一轮对话的话题干扰，误判当前回复（实测日志里
    verifier 输入出现多条 HumanMessage）"""
    mock_llm = MagicMock()
    structured = MagicMock()
    structured.ainvoke = AsyncMock(return_value=Verdict(is_accurate=True, issues=""))
    mock_llm.with_structured_output.return_value = structured

    # 模拟含历史轮次的消息序列：上一轮 user/assistant + 本轮 user/assistant
    messages = [
        HumanMessage(content="上一轮问题：查一下 7 月的账单"),
        AIMessage(content="上一轮回答：7月有2笔"),
        HumanMessage(content="本轮问题：我上个月花了多少钱？"),
        AIMessage(content="本轮回答：上个月花了 70 元"),
    ]
    await run_verdict(mock_llm, messages)

    call_messages = structured.ainvoke.call_args.args[0]
    remaining = call_messages[1:]
    # 只保留最后一个 HumanMessage（本轮问题），历史轮次的用户消息被丢弃
    users = [m for m in remaining if isinstance(m, HumanMessage)]
    assert len(users) == 1
    assert users[0].content == "本轮问题：我上个月花了多少钱？"


def test_build_verdict_input_serializes_payload():
    """_build_verdict_input 返回（精简消息, 序列化输入）；序列化输入首条为
    VERIFY_PROMPT 的 system 消息，其余按 role/content 记录，供全链路
    role=input_verdict 使用"""
    messages = [
        HumanMessage(content="我这个月花了多少钱？"),
        ToolMessage(content="{\"total\": 2}", name="list_expenses", tool_call_id="1"),
        AIMessage(content="这个月花了 70 元"),
    ]
    reduced, serialized = build_verdict_input(messages)

    # 精简消息：前置当前日期参考 SystemMessage，随后是 human/tool/ai
    assert [type(m) for m in reduced] == [SystemMessage, HumanMessage, ToolMessage, AIMessage]
    # 当前日期参考在最前
    assert reduced[0].type == "system"
    assert "当前日期" in reduced[0].content
    # 序列化：首条是质检提示词，第二条是当前日期参考
    assert serialized[0]["role"] == "system"
    assert serialized[0]["content"] == VERIFY_PROMPT
    assert serialized[1]["role"] == "system"
    assert "当前日期" in serialized[1]["content"]
    # 后续按 role/content 记录
    assert [m["role"] for m in serialized[2:]] == ["human", "tool", "ai"]
    assert serialized[2]["content"] == "我这个月花了多少钱？"
    assert serialized[3]["content"] == "{\"total\": 2}"
    assert serialized[4]["content"] == "这个月花了 70 元"


def test_build_verdict_input_keeps_only_current_round_tool_result():
    """质检输入只能包含本轮的工具结果，不能混入历史轮次的工具结果。
    否则质检员会被上一轮的旧数据干扰（与历史 HumanMessage 是同类 bug）"""
    messages = [
        HumanMessage(content="上一轮问题：查7月账单"),
        ToolMessage(content="{\"total\": 1}", name="list_expenses", tool_call_id="1"),
        AIMessage(content="上一轮回答：7月有1笔"),
        HumanMessage(content="本轮问题：查8月账单"),
        ToolMessage(content="{\"total\": 2}", name="list_expenses", tool_call_id="2"),
        AIMessage(content="本轮回答：8月有2笔"),
    ]
    reduced, serialized = build_verdict_input(messages)

    # 只保留当前日期参考 + 本轮用户问题 + 本轮工具结果 + 候选回复
    assert [type(m) for m in reduced] == [SystemMessage, HumanMessage, ToolMessage, AIMessage]
    assert reduced[1].content == "本轮问题：查8月账单"
    assert reduced[2].content == "{\"total\": 2}"
    assert reduced[3].content == "本轮回答：8月有2笔"
    # 序列化输入不包含历史轮次的工具结果
    tool_contents = [m["content"] for m in serialized if m["role"] == "tool"]
    assert tool_contents == ["{\"total\": 2}"]


def test_build_verdict_input_serializes_tool_name_and_args():
    """序列化输入中的 tool 消息应带 name（工具名）与 args（调用参数）：
    同一工具可能被多次调用且参数不同（如查不同日期区间），复盘时靠这两项
    才能看出每条工具结果由哪次调用产生"""
    messages = [
        HumanMessage(content="我这个月花了多少钱？"),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "call_1",
                    "name": "list_expenses_by_date",
                    "args": {"start_date": "2026-08-01", "end_date": "2026-08-15"},
                },
                {
                    "id": "call_2",
                    "name": "list_expenses_by_date",
                    "args": {"start_date": "2026-08-15", "end_date": "2026-08-31"},
                },
            ],
        ),
        ToolMessage(
            content='{"total": 6}',
            name="list_expenses_by_date",
            tool_call_id="call_1",
        ),
        ToolMessage(
            content='{"total": 0}',
            name="list_expenses_by_date",
            tool_call_id="call_2",
        ),
        AIMessage(content="这个月花了 70 元"),
    ]
    reduced, serialized = build_verdict_input(messages)

    # 序列化输入里按 role/content 记录，tool 消息额外带 name 与 args
    tools = [m for m in serialized if m["role"] == "tool"]
    assert len(tools) == 2
    assert tools[0]["name"] == "list_expenses_by_date"
    assert tools[0]["args"] == {
        "start_date": "2026-08-01",
        "end_date": "2026-08-15",
    }
    assert tools[1]["name"] == "list_expenses_by_date"
    assert tools[1]["args"] == {
        "start_date": "2026-08-15",
        "end_date": "2026-08-31",
    }


def test_build_verdict_input_includes_history_reference():
    """传 history_reference 时，质检输入包含完整精纯历史（含用户自我介绍等背景），
    使质检员能理解基于记忆的回复（如称呼用户名），不会被误判"""
    history = [
        HumanMessage(content="我叫小明"),
        AIMessage(content="好的，小明你好！"),
        HumanMessage(content="我的账单是多少？"),  # 本轮 user 已在历史里
    ]
    run_messages = [
        *history,
        ToolMessage(content="{\"total\": 2}", name="list_expenses", tool_call_id="1"),
        AIMessage(content="小明，你这个月有 2 笔支出"),
    ]
    reduced, serialized = build_verdict_input(run_messages, history_reference=history)

    # 参考历史（含自我介绍）进入质检输入
    contents = [m.content for m in reduced]
    assert "我叫小明" in contents
    assert "好的，小明你好！" in contents
    # 候选回复在最后
    assert reduced[-1].content == "小明，你这个月有 2 笔支出"
    # 工具结果也在
    assert any(isinstance(m, ToolMessage) for m in reduced)


def test_build_verdict_input_includes_available_tools():
    """传 available_tools 时，质检输入中应包含可用工具清单（供质检员判断
    "没有可用工具"说法真伪），避免模型被助手谎称无工具欺骗（用户实测担忧）"""
    messages = [
        HumanMessage(content="今天天气如何？"),
        AIMessage(content="我没有查询天气的工具"),
    ]
    reduced, serialized = build_verdict_input(
        messages, available_tools=["get_now_time", "list_expenses"]
    )

    # 可用工具清单进入质检输入（作为参考信息，不作为对话内容）
    combined = " ".join(m.content for m in reduced)
    assert "get_now_time" in combined
    assert "list_expenses" in combined
    # 序列化输入也包含工具清单（供全链路记录 role=input_verdict 复盘）
    serialized_text = " ".join(m["content"] for m in serialized)
    assert "get_now_time" in serialized_text
    assert "list_expenses" in serialized_text


@pytest.mark.asyncio
async def test_run_verdict_passes_available_tools_to_verifier():
    """_run_verdict 把可用工具清单注入质检输入：质检员据此判断"无工具"说法真伪。
    用户问天气（工具列表无天气工具）助手说无工具 -> 允许；用户问账单（列表有
    账单工具）助手说无工具 -> 判不准确。工具清单是判定真伪的事实依据"""
    mock_llm = MagicMock()
    structured = MagicMock()
    structured.ainvoke = AsyncMock(return_value=Verdict(is_accurate=True, issues=""))
    mock_llm.with_structured_output.return_value = structured

    messages = [
        HumanMessage(content="帮我查下账单"),
        AIMessage(content="我没有可用的查询工具"),
    ]
    await run_verdict(mock_llm, messages, available_tools=["list_expenses_by_date"])

    call_messages = structured.ainvoke.call_args.args[0]
    # 可用工具清单随消息注入（在 VERIFY_PROMPT 之后）
    injected = [m.content for m in call_messages[1:]]
    assert any("list_expenses_by_date" in c for c in injected)


@pytest.mark.asyncio
async def test_run_verdict_passes_current_date_to_verifier():
    """_run_verdict 把当前日期注入质检输入：质检员据此判断工具调用参数里的
    年份是否合理（实测 bug：agent 用 2023 年查询当月账单导致查空，若质检员
    不知道当前是 2026 年，会误认为查询无误而放行错误结论）"""
    mock_llm = MagicMock()
    structured = MagicMock()
    structured.ainvoke = AsyncMock(return_value=Verdict(is_accurate=True, issues=""))
    mock_llm.with_structured_output.return_value = structured

    messages = [
        HumanMessage(content="8月14日餐饮花了多少？"),
        AIMessage(content="8月14日没有任何支出"),
    ]
    await run_verdict(mock_llm, messages, current_date="2026-08-15")

    call_messages = structured.ainvoke.call_args.args[0]
    # 当前日期作为参考 SystemMessage 注入（紧随 VERIFY_PROMPT 之后）
    system_msgs = [m for m in call_messages if isinstance(m, SystemMessage)]
    assert len(system_msgs) == 2
    assert system_msgs[0].content == VERIFY_PROMPT
    assert "当前日期：2026-08-15" in system_msgs[1].content
