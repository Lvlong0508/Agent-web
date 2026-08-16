import json
import logging
import time
import uuid

# LangChain 消息类型已不在本文件直接使用：序列化统一委托 events.serialize_message；
# SystemMessage/HumanMessage 仅原内联首轮上下文构造用，已抽到 context 包
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.auth import get_current_user_id_or_raise
from app.repositories.conversation_repo import ConversationRepo
from app.repositories.message_repo import MessageRepo
from app.models.message import Message
from app.models.agent_run import AgentRun
from app.repositories.agent_run_repo import AgentRunRepo
# agent 模块公共 API 统一从包出口导入，避免深层路径散落
# （首轮上下文组装与能力事件系统均已通过包出口暴露，见 spec 2026-08-17-agent-import-optimization-design）
from app.services.agent import (
    CapabilityEvent,
    EventRouter,
    REPLY_ON_VERIFY_FAILED,
    TITLE_COMPLETED_EVENT,
    VERIFIER_VERDICT_EVENT,
    build_agent_graph,
    build_agent_messages,
    serialize_message,
)
from app.tools import get_tools

# 模块级日志器：chat_stream 运行异常时记录含 trace_id 的上下文，便于检索
logger = logging.getLogger(__name__)

# 用户通道统一友好错误文案：SSE error 事件只下发此文案，绝不拼接任何内部细节
# （规格 7.1：用户只需知道出错，管理员详情走 agent_runs 落库）
USER_FRIENDLY_ERROR = "小励出了点问题，请稍后再试吧"


class ChatService:
    """聊天业务层：串联 MongoDB 数据存取和 LangGraph agent 图调用"""

    def __init__(self, db: AsyncIOMotorDatabase, graph=None, session_factory=None):
        self.conv_repo = ConversationRepo(db)
        self.msg_repo = MessageRepo(db)
        self.agent_run_repo = AgentRunRepo(db)  # 全链路运行记录仓库
        # 未显式传入时自动构建 agent 图（测试可注入 mock）；
        # 传入 session_factory 则给图绑定 MySQL 账单工具，让 agent 能调用
        tools = get_tools(session_factory) if session_factory else []
        self.graph = graph or build_agent_graph(self.conv_repo, tools=tools)

    # ----------------------------------------------------------------
    # 对话管理
    # ----------------------------------------------------------------

    async def create_conversation(self) -> dict:
        """创建新对话，返回对话基本信息（归属当前请求用户）"""
        user_id = get_current_user_id_or_raise()
        conv = await self.conv_repo.create(user_id)
        return {"id": conv.id, "title": conv.title, "created_at": conv.created_at}

    async def list_conversations(self) -> list[dict]:
        """列出全部对话（单用户模式下即匿名用户的全部对话）"""
        user_id = get_current_user_id_or_raise()
        convs = await self.conv_repo.list_by_user(user_id)
        return [
            {
                "id": c.id,
                "title": c.title or "新对话",
                "created_at": c.created_at,
                "updated_at": c.updated_at,
            }
            for c in convs
        ]

    async def delete_conversation(self, conv_id: str):
        """删除当前用户的对话及其全部消息（不属于当前用户则报错）"""
        user_id = get_current_user_id_or_raise()
        conv = await self.conv_repo.get_by_id(conv_id, user_id)
        if not conv:
            raise PermissionError("对话不存在或无权访问")
        await self.msg_repo.delete_by_conversation(conv_id)
        await self.conv_repo.delete(conv_id)

    async def get_messages(self, conv_id: str) -> list[dict]:
        """获取当前用户对话的历史消息"""
        user_id = get_current_user_id_or_raise()
        conv = await self.conv_repo.get_by_id(conv_id, user_id)
        if not conv:
            raise PermissionError("对话不存在或无权访问")
        msgs = await self.msg_repo.list_by_conversation(conv_id)
        return [
            {"role": m.role, "content": m.content, "created_at": m.created_at}
            for m in msgs
        ]

    async def _save_run(
        self,
        conv_id: str,
        user_id: str,
        model: str,
        status: str,
        messages: list[dict],
        trace_id: str,
        error: str | None = None,
    ) -> None:
        """落库一条全链路运行记录；落库自身失败时静默跳过（不能干扰主流程）

        trace_id：请求级追踪 ID（必填），管理员凭它把错误链与 emit 事件串联起来（规格 7.1）。
        全部调用点均显式传入，故不设默认值，防止未来调用方漏传
        """
        try:
            await self.agent_run_repo.create(AgentRun(
                conversation_id=conv_id,
                user_id=user_id,
                model=model,
                status=status,
                error=error,
                messages=messages,
                trace_id=trace_id,
            ))
        except Exception:
            # 落库失败（如数据库不可用）不影响聊天主流程：静默跳过
            pass

    # ----------------------------------------------------------------
    # Agent 图驱动聊天
    # ----------------------------------------------------------------

    async def chat_stream(self, conv_id: str, content: str, model: str, thinking: bool = False):
        """
        核心流程：
        1. 校验对话归属（当前请求用户，repo 按 user_id 过滤）
        2. 保存用户消息
        3. 拉取完整历史
        4. 运行 LangGraph agent 图（generate_title → agent），流式产出 token
        5. 流结束后保存 assistant 消息

        thinking：是否开启深度思考（仅通义千问生效），透传给 agent 节点
        """
        # 1. 校验对话归属：repo 查询条件带 user_id，越权直接查不到
        user_id = get_current_user_id_or_raise()
        conv = await self.conv_repo.get_by_id(conv_id, user_id)
        if not conv:
            raise PermissionError("对话不存在或无权访问")

        # 2. 保存用户消息
        user_msg = Message(conversation_id=conv_id, role="user", content=content)
        await self.msg_repo.create(user_msg)

        # 3. 拉取历史消息（含刚保存的用户消息），交给 context 模块组装首轮上下文
        history = await self.msg_repo.list_by_conversation(conv_id)
        # 注入当前日期：agent 构造日期类工具参数（如"8月14日"账单）时才知道
        # 今天是哪年，不会幻觉成往年（实测用 2023 年查询当月账单致查空）
        today = time.strftime("%Y-%m-%d", time.localtime())
        # 首轮上下文组装已抽到 context 包（纯函数，可独立单测）：
        # 系统提示词前置（含日期）+ 历史折叠为 name 标记参考块（滑动窗口）+ 本轮问题独立
        langchain_messages = build_agent_messages(history, today)

        # 4. 运行 agent 图，三流并行消费（规格 5.4）：
        #    - "messages"：逐块产出 LLM token（打字机效果的来源）
        #    - "updates"：每个节点返回后的完整 State 增量，仅用于全链路 trace
        #      落库（自动捕获 tool_calls/tool_call_id/response_metadata），不解析业务字段
        #    - "custom"：能力主动发出的事件，经 EventRouter 订阅后驱动业务行为
        #      （标题推送、verifier 判定 pass/retry/fail）
        full_response = ""  # 存储返回的最终回复
        # 待定回复：当前轮（首轮或重写轮）累积的文本。验证通过前一律不推给前端，
        # 否则不准确的首轮内容会被流式显示后才被替换（实测体验差）
        pending_reply = ""
        # 请求级追踪 ID：注入 config 透传给 emit 与落库，管理员凭它串联错误链
        trace_id = uuid.uuid4().hex
        # 全链路收集：先放入本次用户请求，运行过程中从 updates 流逐节点追加。
        # 用户端 messages 集合保存精简视图（user/assistant），agent_runs
        # 保存完整回放（含工具调用参数与结果），两者各自独立落库
        trace_messages: list[dict] = [{"role": "user", "content": content}]
        run_recorded = False  # 标记是否已成功落库，finally 兜底判断
        # 事件路由：按请求实例化（规格 5.3，严禁全局单例），订阅业务事件。
        # SSE 事件先入队列，再由生成器逐个 yield，保证推送时机受控
        router = EventRouter()
        sse_queue: list[str] = []

        def _enqueue(payload: dict) -> None:
            """把待推送的 SSE 事件入队（非 async，仅供闭包内调用）"""
            sse_queue.append(f"data: {json.dumps(payload, ensure_ascii=False)}\n\n")

        async def on_title(event: CapabilityEvent) -> None:
            """标题事件：非空才推前端侧边栏（避免无谓消息）"""
            title = (event.get("payload") or {}).get("title")
            if title:
                _enqueue({"title": title})

        async def on_verdict(event: CapabilityEvent) -> None:
            """质检判定事件：retry 通知重写并清空待定回复；pass 推送最终版；fail 返回固定文案"""
            # 本函数是 chat_stream 的嵌套闭包，改写外层局部变量必须声明 nonlocal，
            # 否则 `pending_reply = ""` 会创建同名局部变量（Python 闭包赋值陷阱），
            # 导致 retry 清空与 pass 读取都作用在错误变量上
            nonlocal pending_reply, full_response
            result = (event.get("payload") or {}).get("result")
            if result == "retry":
                pending_reply = ""
                _enqueue({"rewriting": True})
            elif result == "pass":
                full_response = pending_reply
                _enqueue({"final": full_response})
            elif result == "fail":
                full_response = REPLY_ON_VERIFY_FAILED
                _enqueue({"final": full_response})

        router.subscribe(TITLE_COMPLETED_EVENT, on_title)
        router.subscribe(VERIFIER_VERDICT_EVENT, on_verdict)

        try:
            async for mode, data in self.graph.astream(
                {
                    "messages": langchain_messages,
                    "conv_id": conv_id,
                    "user_id": user_id,  # 注入当前用户：图节点查询按用户隔离
                    "model": model,
                    "thinking": thinking,
                    # 精纯历史参考（含本轮 user）：来自 context 折叠后的
                    # langchain_messages[1:] = [历史参考块, 本轮问题]，与传给
                    # agent 的记忆一致，无工具轮/重写轮噪音。
                    # 供质检员理解上下文（如历史里用户说过自己叫小明），
                    # 避免质检员只看本轮而误判基于记忆的回复
                    "history_reference": langchain_messages[1:],
                },
                config={"configurable": {"trace_id": trace_id, "thread_id": conv_id}},
                stream_mode=["messages", "updates", "custom"],
            ):
                if mode == "messages":
                    # data 是 (chunk, metadata)，chunk 是 AIMessageChunk
                    chunk, metadata = data
                    # 只接收 agent 节点产出的回复 token。generate_title 节点用非流式
                    # ainvoke 调用 LLM，它的标题输出也会在 messages 流中弹出一个完整
                    # chunk（metadata 标记为 generate_title）；不按节点过滤的话，
                    # 标题会被当成回复 token 拼进气泡内容里
                    if metadata.get("langgraph_node") != "agent":
                        continue
                    # 过滤工具调用轮：流式 chunk（AIMessageChunk）用 tool_call_chunks 判断；
                    # 重写轮非流式产出的是完整 AIMessage，没有 tool_call_chunks 属性，改用
                    # tool_calls 判断。显式判空：无工具调用时两者为 None/空列表；用
                    # `if chunk.tool_call_chunks:` 会把 MagicMock（truthy）误判为有调用
                    tool_call_chunks = getattr(chunk, "tool_call_chunks", None)
                    tool_calls = getattr(chunk, "tool_calls", None)
                    if (
                        (tool_call_chunks is not None and len(tool_call_chunks) > 0)
                        or (tool_calls is not None and len(tool_calls) > 0)
                    ):
                        continue
                    token = chunk.content if isinstance(chunk.content, str) else ""
                    if not token:
                        continue
                    # 验证通过前不推送 token：全部累积进待定回复，
                    # 由 verifier 判定后通过 final 事件一次性推送（见 custom 分支）
                    pending_reply += token
                elif mode == "updates":
                    # updates 仅用于全链路 trace：收集 agent 节点输出（含带 tool_calls
                    # 的中间轮）、工具执行结果、质检输入与判定，不解析业务字段。
                    # 业务行为一律从 custom 事件获取（规格 5.4，消除数据双源）
                    for m in data.get("agent", {}).get("messages", []):
                        trace_messages.append(serialize_message(m))
                    for m in data.get("tools", {}).get("messages", []):
                        trace_messages.append(serialize_message(m))
                    verifier_input = data.get("verifier", {}).get("verdict_input")
                    if verifier_input is not None:
                        # 记录发给质检员的完整输入（role=input_verdict）：含 VERIFY_PROMPT
                        # 与精简后的消息序列，便于事后评估质检效果（看它到底基于什么判定）
                        trace_messages.append(
                            {"role": "input_verdict", "content": verifier_input}
                        )
                    verifier_verdict = data.get("verifier", {}).get("verdict")
                    if verifier_verdict is not None:
                        # 记录质检员结构化判定（role=verdict，content 为 Verdict 字典）。
                        # 至此 trace 完整覆盖：用户提问、agent 各轮回复、工具结果、质检输入、质检判定
                        trace_messages.append(
                            {"role": "verdict", "content": verifier_verdict}
                        )
                elif mode == "custom":
                    # 业务事件：经 EventRouter 分发（标题推送、verifier 判定），
                    # 分发完把队列里的 SSE 事件逐个 yield
                    await router.dispatch(data)
                    while sse_queue:
                        yield sse_queue.pop(0)

            # 5. 保存 assistant 回复
            assistant_msg = Message(
                conversation_id=conv_id, role="assistant", content=full_response
            )
            await self.msg_repo.create(assistant_msg)

            # 全链路落库（status=ok），携带 trace_id 供管理员串联错误链
            await self._save_run(conv_id, user_id, model, "ok", trace_messages, trace_id=trace_id)
            run_recorded = True
        except Exception as e:
            # 运行异常：已收集到的消息序列仍落库并标记 error，便于开发者排查。
            # 注意此时用户消息已保存（在 try 之前），assistant 消息不保存
            # （没有最终回复），符合预期
            await self._save_run(
                conv_id, user_id, model, "error", trace_messages,
                error=str(e), trace_id=trace_id,
            )
            run_recorded = True
            # 用户通道错误分轨：只下发友好文案，不泄漏任何内部细节；
            # 管理员详情已在上方落库（error 字段 + trace_id 可检索）
            logger.exception("chat_stream 运行异常: conv=%s trace_id=%s", conv_id, trace_id)
            yield f"data: {json.dumps({'error': USER_FRIENDLY_ERROR}, ensure_ascii=False)}\n\n"
            raise
        finally:
            # 客户端中途断开（GeneratorExit/CancelledError 是 BaseException，
            # 不会触发上面的 except）时，用户消息已入库但 run 记录缺失：
            # 这里补记一条 error 记录，保持两个集合一致。
            # 落库失败由 _save_run 内部静默吞掉，不干扰生成器关闭流程
            if not run_recorded:
                await self._save_run(
                    conv_id, user_id, model, "error", trace_messages,
                    error="流被中断（客户端断开或取消）", trace_id=trace_id,
                )

        # 6. 发送结束标志
        yield "data: [DONE]\n\n"
