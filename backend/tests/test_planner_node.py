"""planner 节点测试：LLM 调用 + JSON 解析 + 三级降级 + 事件"""

import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.config.agent_settings import agent_settings
from app.services.agent.capabilities.planner.node import make_planner_node


class _FakeTool:
    def __init__(self, name, description):
        self.name = name
        self.description = description


def _sample_plan_json():
    """返回一个合法 planner 输出 JSON 字符串"""
    return json.dumps({
        "intent_l1": "QUERY",
        "intent_l2": "QUERY_BY_DATE",
        "goal": "查询本周账单",
        "plan_steps": [
            {"step_id": 1, "action": "查询本周账单", "suggested_tools": ["list_expenses_by_date"], "depends_on": []},
        ],
        "required_tools": ["list_expenses_by_date"],
        "required_skills": [],
        "confidence": 0.92,
    })


@pytest.mark.asyncio
async def test_planner_node_success():
    """planner 成功：输出规划 + 注入 SystemMessage + 状态 planned"""
    tools = [_FakeTool("list_expenses_by_date", "按日期查询账单")]
    planner = make_planner_node(tools)
    state = {
        "messages": [HumanMessage(content="查一下上周的账单")],
    }

    # fake LLM 返回合法 JSON
    class FakeLLM:
        async def ainvoke(self, *args, **kwargs):
            return AIMessage(content=_sample_plan_json())

    out = await planner(state, llm=FakeLLM())
    assert out["planner_status"] == "planned"
    assert out["planner_result"]["intent_l1"] == "QUERY"
    # 注入的 SystemMessage 带 name=planner 标记
    assert out["messages"][0].name == "planner"
    assert "查询本周账单" in out["messages"][0].content
    # 工具名已清洗为真实名
    assert out["planner_result"]["required_tools"] == ["list_expenses_by_date"]
    assert out["planner_cost_ms"] >= 0  # 成功路径也记录耗时


@pytest.mark.asyncio
async def test_planner_node_json_parse_failure_degrades():
    """JSON 解析失败：降级为跳过，状态 failed，不注入消息"""
    tools = [_FakeTool("create_expense", "新增账单")]
    planner = make_planner_node(tools)
    state = {"messages": [HumanMessage(content="记一笔")]}

    class FakeLLM:
        async def ainvoke(self, *args, **kwargs):
            return AIMessage(content="这不是JSON")

    out = await planner(state, llm=FakeLLM())
    assert out["planner_status"] == "failed"
    assert out["planner_reason"] == "json_parse_error"
    assert out["planner_result"] is None
    assert out["messages"] == []  # 不注入规划消息


@pytest.mark.asyncio
async def test_planner_node_timeout_degrades(monkeypatch):
    """LLM 卡住超过规划超时：节点内部 wait_for 兜底，降级为 failed，reason=timeout

    用 monkeypatch 把 PLANNER_TIMEOUT 调小（0.1s），FakeLLM 睡眠 1s 必然触发
    节点内部的 asyncio.wait_for 超时分支（而非外层取消），并验证 planner_cost_ms 已记录"""
    tools = []
    planner = make_planner_node(tools)
    state = {"messages": [HumanMessage(content="你好")]}

    # 调小超时：原 60s 会让测试等 60 秒，0.1s 即可让节点内部超时分支被真实触发
    monkeypatch.setattr(agent_settings, "PLANNER_TIMEOUT", 0.1)

    class FakeLLM:
        async def ainvoke(self, *args, **kwargs):
            import asyncio
            await asyncio.sleep(1)  # 模拟卡住，超过 0.1s

    out = await planner(state, llm=FakeLLM())
    assert out["planner_status"] == "failed"
    assert out["planner_reason"] == "timeout"
    assert out["planner_result"] is None
    assert out["messages"] == []
    assert out["planner_cost_ms"] >= 0  # 耗时已记录


@pytest.mark.asyncio
async def test_planner_failed_event_carries_cost_time(monkeypatch):
    """失败降级：emit 的事件 payload 带 cost_time_ms（原只有完成事件带耗时）"""
    import app.services.agent.capabilities.planner.node as planner_module

    captured = {}

    def fake_emit(event_type, capability, payload=None, status="progress"):
        captured["event_type"] = event_type
        captured["payload"] = payload or {}

    monkeypatch.setattr(planner_module, "emit", fake_emit)
    tools = []
    planner = make_planner_node(tools)
    state = {"messages": [HumanMessage(content="记一笔")]}

    class FakeLLM:
        async def ainvoke(self, *args, **kwargs):
            return AIMessage(content="这不是JSON")  # 触发 json_parse_error 降级

    out = await planner(state, llm=FakeLLM())
    assert out["planner_status"] == "failed"
    assert captured["event_type"] == "planner.failed"
    assert "cost_time_ms" in captured["payload"]


@pytest.mark.asyncio
async def test_planner_node_low_confidence_still_injects():
    """低置信度：仍注入规划但状态 skipped（agent 自主执行）"""
    tools = []
    planner = make_planner_node(tools)
    state = {"messages": [HumanMessage(content="随便聊聊")]}

    plan = json.loads(_sample_plan_json())
    plan["confidence"] = 0.5  # 低于阈值

    class FakeLLM:
        async def ainvoke(self, *args, **kwargs):
            return AIMessage(content=json.dumps(plan))

    out = await planner(state, llm=FakeLLM())
    assert out["planner_status"] == "skipped"
    assert out["planner_reason"] == "low_confidence"
    assert out["planner_result"] is not None  # 仍保留结果
    assert len(out["messages"]) == 1  # 仍注入（标注低置信度）


@pytest.mark.asyncio
async def test_planner_node_schema_invalid_degrades():
    """schema 校验失败：降级为跳过，状态 failed，reason=schema_invalid"""
    tools = []
    planner = make_planner_node(tools)
    state = {"messages": [HumanMessage(content="记一笔")]}

    bad_plan = json.loads(_sample_plan_json())
    bad_plan["intent_l1"] = "MAKE_MONEY"  # 非法枚举

    class FakeLLM:
        async def ainvoke(self, *args, **kwargs):
            return AIMessage(content=json.dumps(bad_plan))

    out = await planner(state, llm=FakeLLM())
    assert out["planner_status"] == "failed"
    assert out["planner_reason"] == "schema_invalid"
    assert out["planner_result"] is None


@pytest.mark.asyncio
async def test_planner_node_llm_error_degrades():
    """LLM 调用抛任意异常（如 openai 403）：降级为跳过，不向主流程抛错。

    验证器已有 except Exception 降级；planner 同样必须保证"任何失败对主流程
    透明"，否则一次 403 会直接拖垮整条请求（实测崩溃）"""
    tools = []
    planner = make_planner_node(tools)
    state = {"messages": [HumanMessage(content="记一笔")]}

    class FakeLLM:
        async def ainvoke(self, *args, **kwargs):
            raise RuntimeError("模拟 LLM 调用失败（如 API 403）")

    out = await planner(state, llm=FakeLLM())
    assert out["planner_status"] == "failed"
    assert out["planner_reason"] == "llm_error"
    assert out["planner_result"] is None
    assert out["messages"] == []  # 不注入规划消息