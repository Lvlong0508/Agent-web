"""事件系统单元测试：事件信封、序列化、emit 降级、EventRouter 分发与异常隔离"""
import asyncio

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from app.services.agent.events import CapabilityEvent, EventRouter, emit, serialize_message


def test_serialize_message_ai_with_tool_calls():
    """AIMessage 序列化必须保留 tool_calls 完整参数与 role 映射"""
    msg = AIMessage(
        content="让我查一下",
        tool_calls=[{"name": "list_expenses", "args": {"page": 1}, "id": "call_1", "type": "tool_call"}],
    )
    out = serialize_message(msg)
    assert out["role"] == "assistant"
    assert out["content"] == "让我查一下"
    assert out["tool_calls"] == [{"name": "list_expenses", "args": {"page": 1}, "id": "call_1"}]


def test_serialize_message_tool_keeps_call_id_and_name():
    """ToolMessage 序列化必须保留 tool_call_id 与 name（全链路追溯关键）"""
    msg = ToolMessage(content='{"total": 6}', tool_call_id="call_1", name="list_expenses")
    out = serialize_message(msg)
    assert out["role"] == "tool"
    assert out["name"] == "list_expenses"
    assert out["tool_call_id"] == "call_1"


def test_serialize_message_plain_human():
    """普通 HumanMessage 序列化 role 映射为 user"""
    from langchain_core.messages import HumanMessage

    out = serialize_message(HumanMessage(content="你好"))
    assert out["role"] == "user"
    assert out["content"] == "你好"


def test_serialize_message_ai_with_args_json_string():
    """tool_calls 的 args 是 JSON 字符串时应转为 dict（deepseek 评审落地）"""
    # langchain_core 1.4.8 的 pydantic 校验要求 args 必须是 dict，无法直接构造字符串 args，
    # 故先以空 dict 正常构造，再用 object.__setattr__ 绕过校验注入 JSON 字符串，
    # 模拟某些模型/版本返回字符串 args 的真实行为（与本库其它测试同款技巧）
    msg = AIMessage(
        content="",
        tool_calls=[{"name": "list_expenses", "args": {}, "id": "c1"}],
    )
    object.__setattr__(
        msg, "tool_calls", [{"name": "list_expenses", "args": '{"page": 1}', "id": "c1"}]
    )
    out = serialize_message(msg)
    assert out["tool_calls"][0]["args"] == {"page": 1}


@pytest.mark.asyncio
async def test_emit_degrades_outside_stream():
    """非流式上下文（单测）调用 emit 必须降级为 debug，不抛异常"""
    # 非图上下文 get_stream_writer 抛 RuntimeError，emit 内部应吞掉
    emit("test.event", "test_cap", {"a": 1})  # 不应抛异常


@pytest.mark.asyncio
async def test_emit_builds_envelope_and_writes(monkeypatch):
    """emit 快乐路径：信封字段自动填充，writer 被调用且载荷完整"""
    written = []

    def fake_writer(event):
        written.append(event)

    def fake_config():
        return {"configurable": {"trace_id": "trace-abc"}}

    monkeypatch.setattr("app.services.agent.events.get_stream_writer", lambda: fake_writer)
    monkeypatch.setattr("app.services.agent.events.get_config", fake_config)

    emit("verifier.verdict", "verifier", {"result": "pass"}, status="completed")

    assert len(written) == 1
    event = written[0]
    assert event["type"] == "verifier.verdict"
    assert event["capability"] == "verifier"
    assert event["status"] == "completed"
    assert event["payload"] == {"result": "pass"}
    assert event["trace_id"] == "trace-abc"
    assert isinstance(event["seq"], int)
    assert isinstance(event["timestamp"], float)


@pytest.mark.asyncio
async def test_event_router_dispatches_and_isolates_handler_error():
    """EventRouter：订阅分发正确；单个 handler 抛异常不影响其他 handler"""
    router = EventRouter()
    received = []
    calls = {"n": 0}

    async def ok_handler(event):
        received.append(event["payload"]["x"])

    async def boom_handler(event):
        calls["n"] += 1
        raise ValueError("handler 内部错误")

    router.subscribe("test.one", ok_handler)
    router.subscribe("test.one", boom_handler)

    await router.dispatch(CapabilityEvent(type="test.one", capability="t", payload={"x": 42}))

    assert received == [42]      # ok_handler 正常执行
    assert calls["n"] == 1       # boom_handler 被调用但异常被隔离
