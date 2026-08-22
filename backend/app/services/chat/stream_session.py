"""流式会话状态容器：一次聊天请求的可变状态 + 三流消费编排。

背景：chat_stream 原先用 7 个穿插流动的局部变量 + 3 个闭包维护会话状态，
无法脱离方法体单独测试。本模块把状态收拢进 StreamSession（dataclass），
把三流消费循环逻辑收进 StreamOrchestrator，chat_stream 只做编排。
"""

from dataclasses import dataclass, field

from app.services.chat.reply_state import ReplyState
from app.services.chat.sse_serializer import SSEEvent, SSESerializer


@dataclass
class StreamSession:
    """一次流式会话的全部可变状态（构造即初始化，替代闭包捕获的局部变量）。

    reply_state：回复状态机（待定回复/最终版/阶段，见 reply_state.py）
    trace_collector：debug 流采集器（可选注入，缺省 None 时跳过 debug 收集）
    run_recorded：是否已成功落库（finally 兜底判断客户端中途断开）
    sse_events：待序列化的领域事件队列（handler 注入同一对象）
    """

    reply_state: ReplyState = field(default_factory=ReplyState)
    trace_collector: object = None
    run_recorded: bool = False
    sse_events: list[SSEEvent] = field(default_factory=list)

    def collect_token(self, token: str) -> None:
        """累积一个回复 token 到待定回复（验证通过前不推前端）"""
        self.reply_state.pending_reply += token


class StreamOrchestrator:
    """消费 graph.astream 三路流并按 mode 分发到不同处理方法。

    严格保持 astream 原生产出顺序逐条处理，不缓冲、不重排
    （这是 SSE 输出逐字节保真的前提，spec 风险表第 2 条）。
    """

    def __init__(self, graph, session: StreamSession, serializer: SSESerializer, router=None):
        """graph：已编译的 LangGraph（测试可注入 mock）；session：会话状态；
        serializer：SSE 序列化；router：事件路由器（chat_service 注入，缺省不订阅）"""
        self._graph = graph
        self._session = session
        self._serializer = serializer
        self._router = router

    async def run(self, graph_input: dict, config: dict):
        """驱动三流消费循环，逐条产出序列化后的 SSE 文本行。

        graph_input / config：与现 chat_stream 传给 graph.astream 的完全一致
        （messages 输入、conv_id/user_id/model/thinking/history_reference、
        configurable.trace_id/thread_id）。
        """
        async for mode, data in self._graph.astream(
            graph_input,
            config=config,
            stream_mode=["messages", "custom", "debug"],
        ):
            if mode == "messages":
                self._handle_messages(data)
            elif mode == "debug":
                # debug 流：每节点 task/task_result → TraceCollector 采集原始 Step
                # 记录（零硬编码节点名，spec §5.1）；未注入采集器则跳过
                if self._session.trace_collector is not None:
                    self._session.trace_collector.process_debug_event(data)
            elif mode == "custom":
                # 业务事件：经订阅 handler 产出领域事件到 session.sse_events，
                # 再逐个取出序列化为 SSE 行 yield（保持原推送时机受控）
                await self._dispatch(data)
                while self._session.sse_events:
                    yield self._serializer.serialize(self._session.sse_events.pop(0))

    async def _dispatch(self, event: dict) -> None:
        """事件分发：经 EventRouter 交给订阅 handler 驱动业务行为（标题/质检判定）"""
        if self._router is not None:
            await self._router.dispatch(event)

    def _handle_messages(self, data) -> None:
        """处理 messages 流：过滤非 agent 节点与工具调用轮，累积回复 token。

        过滤规则（与原 chat_stream 一致）：
        - metadata.langgraph_node 必须为 "agent"（排除 generate_title 的标题输出）
        - 含 tool_call_chunks（流式）或 tool_calls（非流式）的轮次跳过
        - 显式判空，避免 MagicMock（truthy）误判为有工具调用
        """
        chunk, metadata = data
        if metadata.get("langgraph_node") != "agent":
            return
        tool_call_chunks = getattr(chunk, "tool_call_chunks", None)
        tool_calls = getattr(chunk, "tool_calls", None)
        if (
            (tool_call_chunks is not None and len(tool_call_chunks) > 0)
            or (tool_calls is not None and len(tool_calls) > 0)
        ):
            return
        token = chunk.content if isinstance(chunk.content, str) else ""
        if not token:
            return
        self._session.collect_token(token)