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


def test_serialize_message_ai_keeps_metrics_metadata():
    """全链路记录补全性能指标：AIMessage 序列化保留 response_metadata 的
    model/token 到 metadata 字段（不再丢弃），供管理员查看成本。
    注意 response_metadata 的记录分支在 tool_calls 块内，须带 tool_calls
    才走到真实代码路径（中间工具调用轮才带 response_metadata）。"""
    msg = AIMessage(
        content="让我查一下",
        tool_calls=[{
            "name": "list_expenses",
            "args": {"page": 1},
            "id": "call_1",
            "type": "tool_call",
        }],
        response_metadata={
            "token_usage": {"completion_tokens": 86, "prompt_tokens": 1798},
            "model_name": "qwen3.7-flash",
            "finish_reason": "tool_calls",
        },
    )
    out = serialize_message(msg)
    assert "response_metadata" not in out   # 原始键不落库（防冗余）
    assert out["role"] == "assistant"
    assert out["content"] == "让我查一下"
    assert out["tool_calls"][0]["name"] == "list_expenses"
    # 指标进 metadata 字段（兼容 prompt_tokens/completion_tokens 命名）
    assert out["metadata"]["model"] == "qwen3.7-flash"
    assert out["metadata"]["input_tokens"] == 1798
    assert out["metadata"]["output_tokens"] == 86
    assert out["metadata"]["finish_reason"] == "tool_calls"


def test_serialize_message_keeps_usage_metadata():
    """AIMessage 带 input_tokens/output_tokens 命名：同样保留进 metadata"""
    msg = AIMessage(
        content="hi",
        response_metadata={"model_name": "qwen-max",
                           "token_usage": {"input_tokens": 12, "output_tokens": 3}},
    )
    entry = serialize_message(msg)
    assert entry["role"] == "assistant"
    assert entry["metadata"]["model"] == "qwen-max"
    assert entry["metadata"]["input_tokens"] == 12
    assert entry["metadata"]["output_tokens"] == 3


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


def test_event_router_subscribed_no_warning(caplog):
    """订阅 planner.failed 后 dispatch 不再打"未订阅"警告。

    回归保护：chat_service 已订阅 planner 事件，若订阅遗漏，dispatch 会
    打 warning"收到未订阅的事件类型"，制造日志噪音并掩盖真实问题"""
    import logging

    router = EventRouter()
    received = []

    async def handler(event):
        received.append(event)

    router.subscribe("planner.failed", handler)

    asyncio.run(router.dispatch({"type": "planner.failed", "payload": {}}))

    assert received, "订阅的 handler 必须被调用"
    assert not any("未订阅" in r.message for r in caplog.records)
