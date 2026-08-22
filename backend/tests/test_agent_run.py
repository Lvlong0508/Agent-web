"""agent 运行全链路记录测试：模型默认值、数据访问层与 chat_stream 落库"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from app.auth import current_user_id
from app.config import agent_settings
from app.config import settings
from app.models.agent_run import AgentRun
from app.models.conversation import Conversation
from app.repositories.agent_run_repo import AgentRunRepo
from app.schemas.agent_run import AgentRunPage
from app.services.agent_run_service import AgentRunService
from app.services.chat_service import ChatService


def test_agent_run_model_defaults():
    """模型默认值：status=ok、无错误、消息列表为空、自动生成 id"""
    run = AgentRun(conversation_id="c1", user_id="u1", model="ollama")
    assert run.status == "ok"
    assert run.error is None
    assert run.messages == []
    assert run.id  # _id 别名自动生成 uuid


@pytest.mark.asyncio
async def test_agent_run_repo_create():
    """create 把 run 按别名序列化插入集合"""
    db = MagicMock()
    repo = AgentRunRepo(db)
    repo.collection.insert_one = AsyncMock(return_value=None)
    run = AgentRun(conversation_id="c1", user_id="u1", model="ollama")

    result = await repo.create(run)

    assert result is run
    repo.collection.insert_one.assert_awaited_once_with(run.model_dump(by_alias=True))


@pytest.mark.asyncio
async def test_agent_run_repo_list_by_conversation():
    """按 conversation_id 查询并按 created_at 升序返回"""
    db = MagicMock()
    now = datetime.now(timezone.utc)
    repo = AgentRunRepo(db)
    repo.collection.find.return_value.sort.return_value.to_list = AsyncMock(
        return_value=[{
            "_id": "r1", "conversation_id": "c1", "user_id": "u1",
            "model": "ollama", "status": "ok", "error": None,
            "messages": [], "created_at": now,
        }]
    )

    runs = await repo.list_by_conversation("c1")

    assert len(runs) == 1
    assert runs[0].conversation_id == "c1"
    # 查询必须带 conversation_id 过滤并按时间升序（回放顺序）
    repo.collection.find.assert_called_once_with({"conversation_id": "c1"})
    # 断言按创建时间升序排序（保证回放顺序）
    repo.collection.find.return_value.sort.assert_called_once_with("created_at", 1)


@pytest.mark.asyncio
async def test_agent_run_repo_list_paged():
    """分页查询：先 count_documents 统计总数，再按 created_at 倒序 skip/limit"""
    db = MagicMock()
    now = datetime.now(timezone.utc)
    repo = AgentRunRepo(db)
    # 分页链：find → sort → skip → limit → to_list；count_documents 独立统计总数
    repo.collection.count_documents = AsyncMock(return_value=3)
    repo.collection.find.return_value.sort.return_value.skip.return_value.limit.return_value.to_list = AsyncMock(
        return_value=[{
            "_id": "r1", "conversation_id": "c1", "user_id": "u1",
            "model": "ollama", "status": "ok", "error": None,
            "messages": [], "created_at": now,
        }]
    )

    items, total = await repo.list_paged({"user_id": "u1"}, 2, 10)

    # 过滤条件原样传给 count 与 find
    repo.collection.count_documents.assert_awaited_once_with({"user_id": "u1"})
    repo.collection.find.assert_called_once_with({"user_id": "u1"})
    # 创建时间倒序（最新在前），第 2 页跳过前 10 条、取 10 条
    repo.collection.find.return_value.sort.assert_called_once_with("created_at", -1)
    repo.collection.find.return_value.sort.return_value.skip.assert_called_once_with(10)
    repo.collection.find.return_value.sort.return_value.skip.return_value.limit.assert_called_once_with(10)
    assert total == 3
    assert len(items) == 1
    assert items[0].conversation_id == "c1"


@pytest.mark.asyncio
async def test_agent_run_repo_delete_many():
    """批量删除：$in 命中即删，返回实际删除条数"""
    db = MagicMock()
    repo = AgentRunRepo(db)
    result_mock = MagicMock()
    result_mock.deleted_count = 2  # r3 不存在，实际只删掉 2 条
    repo.collection.delete_many = AsyncMock(return_value=result_mock)

    n = await repo.delete_many(["r1", "r2", "r3"])

    assert n == 2
    repo.collection.delete_many.assert_awaited_once_with({"_id": {"$in": ["r1", "r2", "r3"]}})


@pytest.mark.asyncio
async def test_chat_stream_saves_full_trace_without_tools():
    """无工具调用：run 记录含 entry Step 与 agent Step，status=ok"""
    token = current_user_id.set("anonymous")
    try:
        conv = Conversation(_id="c1", user_id="anonymous")
        service = ChatService(MagicMock())
        service.agent_run_service = MagicMock()
        service.agent_run_service.create = AsyncMock(return_value=None)
        service.conv_repo.get_by_id = AsyncMock(return_value=conv)
        service.msg_repo.list_by_conversation = AsyncMock(return_value=[])
        service.msg_repo.create = AsyncMock(return_value=None)

        final_msg = AIMessage(content="你好，很高兴认识你")
        final_chunk = MagicMock()
        final_chunk.content = "你好，很高兴认识你"
        final_chunk.tool_call_chunks = None

        async def fake_astream(input, **kwargs):
            # messages 流：agent token（用户端推送）
            yield ("messages", (final_chunk, {"langgraph_node": "agent"}))
            # debug 流：agent 节点的完整生命周期（输入 + 输出）
            yield ("debug", {"type": "task", "step": 1, "timestamp": "2026-08-22T00:00:00.000Z",
                             "payload": {"id": "id-a", "name": "agent", "input": {"messages": []}}})
            yield ("debug", {"type": "task_result", "step": 1, "timestamp": "2026-08-22T00:00:00.500Z",
                             "payload": {"id": "id-a", "name": "agent",
                                         "result": {"messages": [final_msg]}, "error": None}})

        service.graph = MagicMock()
        service.graph.astream = fake_astream

        async for _ in service.chat_stream("c1", "你好", agent_settings.MODEL_OLLAMA):
            pass

        # 断言落库的 run 记录内容（chat_service 以 kwargs 调 service.create）
        run = service.agent_run_service.create.await_args.kwargs
        assert run["status"] == "ok"
        assert run["conversation_id"] == "c1"
        assert run["model"] == agent_settings.MODEL_OLLAMA
        # 三层结构：entry 首条 + agent Step（debug 流采集，输出为最终回复）
        assert run["entry"]["step_type"] == "entry"
        assert [s["node_name"] for s in run["raw_steps"]] == ["agent"]
        agent_step = run["raw_steps"][0]
        assert agent_step["duration_ms"] == 500
        assert agent_step["output"]["messages"][0]["content"] == "你好，很高兴认识你"
    finally:
        current_user_id.reset(token)


@pytest.mark.asyncio
async def test_chat_stream_saves_full_trace_with_tools():
    """含工具调用：run 记录含 user/assistant(tool_calls)/tool/assistant 四类消息"""
    token = current_user_id.set("anonymous")
    try:
        conv = Conversation(_id="c1", user_id="anonymous")
        service = ChatService(MagicMock())
        service.agent_run_service = MagicMock()
        service.agent_run_service.create = AsyncMock(return_value=None)
        service.conv_repo.get_by_id = AsyncMock(return_value=conv)
        service.msg_repo.list_by_conversation = AsyncMock(return_value=[])
        service.msg_repo.create = AsyncMock(return_value=None)

        # 模拟一次真实工具调用：agent 决定调用 → 工具执行 → agent 最终回复
        tool_call_msg = AIMessage(
            content="正在查询账单...",
            tool_calls=[{
                "name": "list_expenses",
                "args": {"page": 1, "page_size": 5},
                "id": "call_1",
                "type": "tool_call",
            }],
        )
        tool_result_msg = ToolMessage(
            content='{"items": [], "total": 0, "page": 1, "page_size": 5, "total_pages": 0}',
            name="list_expenses",
            tool_call_id="call_1",
        )
        final_msg = AIMessage(content="你共有 0 条账单")

        async def fake_astream(input, **kwargs):
            # debug 流按执行顺序产出三个节点的完整生命周期（输入 + 输出）
            yield ("debug", {"type": "task", "step": 1, "timestamp": "2026-08-22T00:00:00.000Z",
                             "payload": {"id": "id-a", "name": "agent", "input": {"messages": []}}})
            yield ("debug", {"type": "task_result", "step": 1, "timestamp": "2026-08-22T00:00:00.100Z",
                             "payload": {"id": "id-a", "name": "agent",
                                         "result": {"messages": [tool_call_msg]}, "error": None}})
            yield ("debug", {"type": "task", "step": 2, "timestamp": "2026-08-22T00:00:00.100Z",
                             "payload": {"id": "id-b", "name": "tools", "input": {"messages": []}}})
            yield ("debug", {"type": "task_result", "step": 2, "timestamp": "2026-08-22T00:00:00.200Z",
                             "payload": {"id": "id-b", "name": "tools",
                                         "result": {"messages": [tool_result_msg]}, "error": None}})
            yield ("debug", {"type": "task", "step": 3, "timestamp": "2026-08-22T00:00:00.200Z",
                             "payload": {"id": "id-c", "name": "agent", "input": {"messages": []}}})
            yield ("debug", {"type": "task_result", "step": 3, "timestamp": "2026-08-22T00:00:00.300Z",
                             "payload": {"id": "id-c", "name": "agent",
                                         "result": {"messages": [final_msg]}, "error": None}})
            # 最终回复轮没有工具调用，token 走 messages 流推给用户端
            final_chunk = MagicMock()
            final_chunk.content = "你共有 0 条账单"
            final_chunk.tool_call_chunks = None
            yield ("messages", (final_chunk, {"langgraph_node": "agent"}))

        service.graph = MagicMock()
        service.graph.astream = fake_astream

        async for _ in service.chat_stream("c1", "查一下账单", agent_settings.MODEL_OLLAMA):
            pass

        run = service.agent_run_service.create.await_args.kwargs
        steps = run["raw_steps"]
        # 三个节点按执行顺序完整记录（含工具调用链路）
        assert [s["node_name"] for s in steps] == ["agent", "tools", "agent"]
        # 第一个 agent Step：消息携带工具调用参数
        agent1_out = steps[0]["output"]["messages"][0]
        assert agent1_out["role"] == "assistant"
        assert agent1_out["tool_calls"][0]["name"] == "list_expenses"
        assert agent1_out["tool_calls"][0]["args"] == {"page": 1, "page_size": 5}
        # tools Step：工具结果消息带工具名与返回内容
        tools_out = steps[1]["output"]["messages"][0]
        assert tools_out["role"] == "tool"
        assert tools_out["name"] == "list_expenses"
        assert "total" in tools_out["content"]
        # 最终回复 Step
        assert steps[2]["output"]["messages"][0]["content"] == "你共有 0 条账单"
    finally:
        current_user_id.reset(token)


@pytest.mark.asyncio
async def test_chat_stream_records_error_run():
    """运行抛异常时：run 记录 status=error 并保存错误信息"""
    token = current_user_id.set("anonymous")
    try:
        conv = Conversation(_id="c1", user_id="anonymous")
        service = ChatService(MagicMock())
        service.agent_run_service = MagicMock()
        service.agent_run_service.create = AsyncMock(return_value=None)
        service.conv_repo.get_by_id = AsyncMock(return_value=conv)
        service.msg_repo.list_by_conversation = AsyncMock(return_value=[])
        service.msg_repo.create = AsyncMock(return_value=None)

        async def fake_astream(input, **kwargs):
            # 先产出一条 agent 中间输出（debug 流），然后模拟模型调用崩溃
            yield ("debug", {"type": "task", "step": 1, "timestamp": "2026-08-22T00:00:00.000Z",
                             "payload": {"id": "id-a", "name": "agent", "input": {"messages": []}}})
            yield ("debug", {"type": "task_result", "step": 1, "timestamp": "2026-08-22T00:00:00.100Z",
                             "payload": {"id": "id-a", "name": "agent",
                                         "result": {"messages": [AIMessage(content="正在查询...")]},
                                         "error": None}})
            raise RuntimeError("模型调用超时")

        service.graph = MagicMock()
        service.graph.astream = fake_astream

        with pytest.raises(RuntimeError):
            async for _ in service.chat_stream("c1", "你好", agent_settings.MODEL_OLLAMA):
                pass

        run = service.agent_run_service.create.await_args.kwargs
        assert run["status"] == "error"
        assert "模型调用超时" in run["error"]
        # 已收集到的节点记录仍保留（agent Step 已采集）
        assert [s["node_name"] for s in run["raw_steps"]] == ["agent"]
        # 只落库一条 error 记录（finally 兜底不再补记），防止重复写入
        assert service.agent_run_service.create.call_count == 1
    finally:
        current_user_id.reset(token)


@pytest.mark.asyncio
async def test_chat_stream_records_interrupted_run():
    """客户端中途断开（生成器被 close）：finally 兜底落库一条 error 记录"""
    token = current_user_id.set("anonymous")
    try:
        conv = Conversation(_id="c1", user_id="anonymous")
        service = ChatService(MagicMock())
        service.agent_run_service = MagicMock()
        service.agent_run_service.create = AsyncMock(return_value=None)
        service.conv_repo.get_by_id = AsyncMock(return_value=conv)
        service.msg_repo.list_by_conversation = AsyncMock(return_value=[])
        service.msg_repo.create = AsyncMock(return_value=None)

        final_msg = AIMessage(content="部分内容")
        final_chunk = MagicMock()
        final_chunk.content = "部分内容"
        final_chunk.tool_call_chunks = None

        async def fake_astream(input, **kwargs):
            # 先产出标题 custom 事件让 chat_stream 有可消费的 yield 点（dispatch 后
            # SSE 入队逐个 yield）；若只产出 messages 累积块，chat_stream 会在 agent
            # 阶段不 yield，直接跑完全程，首次 __anext__ 就返回 [DONE]，无法模拟
            # "消费一半后断开"
            yield ("custom", {"type": "title.completed", "capability": "title",
                              "status": "completed", "payload": {"title": "标题"}})
            yield ("messages", (final_chunk, {"langgraph_node": "agent"}))
            yield ("debug", {"type": "task", "step": 1, "timestamp": "2026-08-22T00:00:00.000Z",
                             "payload": {"id": "id-a", "name": "agent", "input": {"messages": []}}})
            yield ("debug", {"type": "task_result", "step": 1, "timestamp": "2026-08-22T00:00:00.100Z",
                             "payload": {"id": "id-a", "name": "agent",
                                         "result": {"messages": [final_msg]}, "error": None}})

        service.graph = MagicMock()
        service.graph.astream = fake_astream

        # 消费一段后主动关闭生成器，模拟客户端断开
        agen = service.chat_stream("c1", "你好", agent_settings.MODEL_OLLAMA)
        await agen.__anext__()  # 消费第一个事件（标题），生成器停在循环中间
        await agen.aclose()     # 模拟客户端中途断开

        run = service.agent_run_service.create.await_args.kwargs
        assert run["status"] == "error"
        assert "流被中断" in run["error"]
        # 流中断时生成器在 custom 处被关闭，debug 事件尚未消费 → raw_steps 为空；
        # 但 entry（首轮上下文）在运行前已生成，仍随 error 记录落库
        assert run["raw_steps"] == []
        assert run["entry"]["step_type"] == "entry"
    finally:
        current_user_id.reset(token)


@pytest.mark.asyncio
async def test_chat_stream_keep_original_exception_when_save_fails():
    """错误落库自身抛错时：不能遮蔽原始异常，原始异常仍向上传播"""
    token = current_user_id.set("anonymous")
    try:
        conv = Conversation(_id="c1", user_id="anonymous")
        service = ChatService(MagicMock())
        service.agent_run_service = MagicMock()
        service.agent_run_service.create = AsyncMock(side_effect=RuntimeError("落库也失败"))
        service.conv_repo.get_by_id = AsyncMock(return_value=conv)
        service.msg_repo.list_by_conversation = AsyncMock(return_value=[])
        service.msg_repo.create = AsyncMock(return_value=None)

        async def fake_astream(input, **kwargs):
            # 必须含一个 yield 使函数成为异步生成器（async for 需要迭代器而非协程）；
            # 用不可达分支保证首次迭代立即抛模型异常
            if False:
                yield
            raise RuntimeError("模型调用超时")

        service.graph = MagicMock()
        service.graph.astream = fake_astream

        with pytest.raises(RuntimeError) as exc_info:
            async for _ in service.chat_stream("c1", "你好", agent_settings.MODEL_OLLAMA):
                pass

        # 原始异常（模型调用超时）必须向上传播，而不是被落库异常（落库也失败）顶替
        assert "模型调用超时" in str(exc_info.value)
    finally:
        current_user_id.reset(token)


@pytest.mark.asyncio
async def test_chat_stream_records_verifier_verdict_in_trace():
    """质检员结构化判定应记录进全链路：追加 role=verdict 条目（content 为 Verdict 字典）"""
    token = current_user_id.set("anonymous")
    try:
        conv = Conversation(_id="c1", user_id="anonymous")
        service = ChatService(MagicMock())
        service.agent_run_service = MagicMock()
        service.agent_run_service.create = AsyncMock(return_value=None)
        service.conv_repo.get_by_id = AsyncMock(return_value=conv)
        service.msg_repo.list_by_conversation = AsyncMock(return_value=[])
        service.msg_repo.create = AsyncMock(return_value=None)

        async def fake_astream(input, **kwargs):
            """verifier 节点产出 verdict（Verdict 字典）与 verdict_input（序列化输入）"""
            yield ("debug", {"type": "task", "step": 1, "timestamp": "2026-08-22T00:00:00.000Z",
                             "payload": {"id": "id-v", "name": "verifier", "input": {"messages": []}}})
            yield ("debug", {"type": "task_result", "step": 1, "timestamp": "2026-08-22T00:00:00.100Z",
                             "payload": {"id": "id-v", "name": "verifier",
                                         "result": {
                                             "verification_result": "pass",
                                             "verdict": {"is_accurate": True, "issues": ""},
                                             "verdict_input": [
                                                 {"role": "system", "content": "质检提示词"},
                                                 {"role": "human", "content": "我这个月花了多少钱？"},
                                                 {"role": "ai", "content": "这个月花了 70 元"},
                                             ],
                                         },
                                         "error": None}})

        service.graph = MagicMock()
        service.graph.astream = fake_astream

        async for _ in service.chat_stream("c1", "你好", agent_settings.MODEL_OLLAMA):
            pass

        run = service.agent_run_service.create.await_args.kwargs
        # 三层结构：verifier Step 的 output 含质检判定与发给质检员的输入记录
        verifier_steps = [s for s in run["raw_steps"] if s["node_name"] == "verifier"]
        assert len(verifier_steps) == 1
        out = verifier_steps[0]["output"]
        assert out["verdict"] == {"is_accurate": True, "issues": ""}
        assert out["verification_result"] == "pass"
        assert out["verdict_input"][0]["role"] == "system"
        assert out["verdict_input"][1]["content"] == "我这个月花了多少钱？"
    finally:
        current_user_id.reset(token)


@pytest.mark.asyncio
async def test_agent_run_service_create():
    """插入：service 内部把 raw_steps 组装为三层 AgentRun 后交给 repo"""
    db = MagicMock()
    service = AgentRunService(db)
    service.repo.create = AsyncMock(return_value=None)

    result = await service.create(
        conversation_id="c1", user_id="u1", model="ollama",
        status="ok", raw_steps=[], trace_id="t1", error=None,
    )

    # 透传完整 AgentRun 对象（默认值：steps 空、status ok、error None）
    run = service.repo.create.await_args.args[0]
    assert isinstance(run, AgentRun)
    assert run.conversation_id == "c1"
    assert run.trace_id == "t1"
    assert run.steps == []
    assert result is None  # 返回 repo.create 的结果


@pytest.mark.asyncio
async def test_agent_run_service_create_defaults():
    """插入默认值：status=ok、steps 空、trace_id 空串、error None"""
    db = MagicMock()
    service = AgentRunService(db)
    service.repo.create = AsyncMock(return_value=None)

    await service.create(conversation_id="c1", user_id="u1", model="ollama")

    run = service.repo.create.await_args.args[0]
    assert run.status == "ok"
    assert run.steps == []
    assert run.trace_id == ""
    assert run.error is None


@pytest.mark.asyncio
async def test_agent_run_service_list():
    """分页查询：默认全量；按 user_id/conversation_id 组装过滤；分页参数钳制"""
    db = MagicMock()
    service = AgentRunService(db)
    now = datetime.now(timezone.utc)
    items = [AgentRun(conversation_id="c1", user_id="u1", model="ollama")]
    service.repo.list_paged = AsyncMock(return_value=(items, 3))

    # 默认：不过滤、page=1、page_size=20
    page = await service.list()
    service.repo.list_paged.assert_awaited_once_with({}, 1, 20)
    assert page.total == 3
    assert page.total_pages == 1  # ceil(3/20) = 1
    assert page.items == items
    assert page.page == 1
    assert page.page_size == 20
    assert isinstance(page, AgentRunPage)

    # 可选过滤 + 参数钳制：page 0→1，page_size 1000→100
    page = await service.list(page=0, page_size=1000, user_id="u1", conversation_id="c1")
    service.repo.list_paged.assert_called_with({"user_id": "u1", "conversation_id": "c1"}, 1, 100)
    assert page.page == 1
    assert page.page_size == 100


@pytest.mark.asyncio
async def test_agent_run_service_delete_many():
    """批量删除：透传 run_ids 到 repo，返回删除条数；空列表直接返回 0 不查库"""
    db = MagicMock()
    service = AgentRunService(db)
    service.repo.delete_many = AsyncMock(return_value=2)

    n = await service.delete_many(["r1", "r2"])
    assert n == 2
    service.repo.delete_many.assert_awaited_once_with(["r1", "r2"])

    # 空列表早退：不发无意义的 Mongo 查询
    service.repo.delete_many = AsyncMock()
    n = await service.delete_many([])
    assert n == 0
    service.repo.delete_many.assert_not_called()
