"""planner 节点测试：LLM 调用 + JSON 解析 + 三级降级 + 事件"""

import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage

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
async def test_planner_node_timeout_degrades():
    """LLM 超时：降级为跳过，状态 failed，reason=timeout"""
    tools = []
    planner = make_planner_node(tools)
    state = {"messages": [HumanMessage(content="你好")]}

    class FakeLLM:
        async def ainvoke(self, *args, **kwargs):
            import asyncio

            await asyncio.sleep(10)  # 模拟卡住

    import asyncio

    with pytest.raises(asyncio.TimeoutError):
        # 超时由外层 asyncio.wait_for 保障，节点内部 wait_for(PLANNER_TIMEOUT=20s)
        # 会晚于外层 1s 触发，因此外层先抛 TimeoutError
        out = await asyncio.wait_for(planner(state, llm=FakeLLM()), timeout=1)


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