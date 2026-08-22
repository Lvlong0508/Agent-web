"""title 节点降级标记测试：异常时仍写 generated_title 字段（让 Step 可见）"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from langgraph.graph import StateGraph

from app.services.agent.capabilities.title import TitleCapability


@pytest.mark.asyncio
async def test_title_node_degraded_still_returns_field():
    """标题 LLM 抛异常：节点返回 generated_title=""，不向主流程抛错"""
    conv = MagicMock()
    conv.title = ""   # 标题为空，触发生成路径
    conv_repo = MagicMock()
    conv_repo.get_by_id = AsyncMock(return_value=conv)
    conv_repo.update_title = AsyncMock(return_value=None)

    cap = TitleCapability(conv_repo)
    builder = StateGraph(dict)
    cap.register_nodes(builder)
    node = builder.nodes["generate_title"].runnable  # 取节点可运行体（RunnableLambda）

    # 标题生成抛异常（模拟模型挂掉）：节点必须静默降级并返回空标题字段
    state = {"conv_id": "c1", "user_id": "u1", "model": "ollama",
             "messages": [MagicMock(type="human", content="hi")]}
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "app.services.agent.capabilities.title.node._generate_title_if_empty",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("标题模型挂了")),
        )
        out = await node.ainvoke(state)

    # 降级不抛错、写回空标题字段（Step 能呈现该节点执行过，spec §5.3）
    assert "generated_title" in out
    assert out["generated_title"] == ""