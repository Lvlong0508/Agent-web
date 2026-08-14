import json

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.auth import get_current_user_id_or_raise
from app.repositories.conversation_repo import ConversationRepo
from app.repositories.message_repo import MessageRepo
from app.models.message import Message
from app.models.agent_run import AgentRun
from app.repositories.agent_run_repo import AgentRunRepo
from app.services.agent_graph import build_agent_graph
from app.services.prompts import REPLY_ON_VERIFY_FAILED, SYSTEM_PROMPT
from app.tools import get_tools


def _langchain_msg_to_trace(msg) -> dict:
    """把 LangChain 消息转成全链路记录用的字典（保持时间顺序）"""
    # ToolMessage：工具执行结果，带上工具名便于开发者定位
    if isinstance(msg, ToolMessage):
        return {"role": "tool", "content": msg.content, "name": msg.name}
    # AIMessage：可能是带 tool_calls 的中间轮，也可能是最终回复轮
    if isinstance(msg, AIMessage):
        entry = {"role": "assistant", "content": msg.content}
        if msg.tool_calls:
            entry["tool_calls"] = [
                {"name": tc["name"], "args": tc["args"]} for tc in msg.tool_calls
            ]
        return entry
    # 其他角色兜底
    return {"role": getattr(msg, "type", "unknown"), "content": msg.content}


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
        error: str | None = None,
    ) -> None:
        """落库一条全链路运行记录；落库自身失败时静默跳过（不能干扰主流程）"""
        try:
            await self.agent_run_repo.create(AgentRun(
                conversation_id=conv_id,
                user_id=user_id,
                model=model,
                status=status,
                error=error,
                messages=messages,
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

        # 3. 拉取历史消息（含刚保存的用户消息），转为 LangChain 消息
        history = await self.msg_repo.list_by_conversation(conv_id)
        # 上下文窗口：系统提示词只在这里注入一次、排在最前；
        # 历史消息只存 user/assistant 角色，因此不会重复添加
        langchain_messages = [SystemMessage(content=SYSTEM_PROMPT)]
        for m in history:
            if m.role == "user":
                langchain_messages.append(HumanMessage(content=m.content))
            elif m.role == "assistant":
                langchain_messages.append(AIMessage(content=m.content))

        # 4. 运行 agent 图，同时监听两种流模式：
        #    - "messages"：逐块产出 LLM token（打字机效果的来源）
        #    - "updates"：每个节点结束后返回的增量状态，用于拿到 generate_title
        #      节点生成的新标题并实时推给前端（否则侧边栏要手动刷新才更新）
        full_response = ""  # 存储返回的最终回复
        # 待定回复：当前轮（首轮或重写轮）累积的文本。验证通过前一律不推给前端，
        # 否则不准确的首轮内容会被流式显示后才被替换（实测体验差）
        pending_reply = ""
        # 全链路收集：先放入本次用户请求，运行过程中逐节点追加。
        # 用户端 messages 集合保存精简视图（user/assistant），agent_runs
        # 保存完整回放（含工具调用参数与结果），两者各自独立落库
        trace_messages: list[dict] = [{"role": "user", "content": content}]
        run_recorded = False  # 标记是否已成功落库，finally 兜底判断
        try:
            async for mode, data in self.graph.astream(
                {
                    "messages": langchain_messages,
                    "conv_id": conv_id,
                    "user_id": user_id,  # 注入当前用户：图节点查询按用户隔离
                    "model": model,
                    "thinking": thinking,
                },
                stream_mode=["messages", "updates"],
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
                    # 由 verifier 判定后通过 final 事件一次性推送（见 updates 分支）
                    pending_reply += token
                elif mode == "updates":
                    # data 形如 {"generate_title": {"generated_title": "标题"}}；
                    # 仅在标题节点真生成了标题时（非空）推送事件，避免无谓消息
                    title = data.get("generate_title", {}).get("generated_title")
                    if title:
                        yield f"data: {json.dumps({'title': title}, ensure_ascii=False)}\n\n"
                    # 收集全链路：agent 节点输出的每条消息（含带 tool_calls 的中间轮
                    # 和不带工具调用的最终回复轮）
                    for m in data.get("agent", {}).get("messages", []):
                        trace_messages.append(_langchain_msg_to_trace(m))
                    # 收集工具执行结果（ToolMessage）
                    for m in data.get("tools", {}).get("messages", []):
                        trace_messages.append(_langchain_msg_to_trace(m))
                    # 验证节点结果：retry → 通知前端进入重写并清空待定回复；
                    # pass → 推送最终版；fail → 超限返回固定文案（不再循环）
                    result = data.get("verifier", {}).get("verification_result")
                    # 记录质检员结构化判定到全链路（role=verdict，content 为 Verdict 字典）。
                    # 至此 trace 完整覆盖：用户提问、agent 各轮回复、工具结果、质检判定
                    verifier_verdict = data.get("verifier", {}).get("verdict")
                    if verifier_verdict is not None:
                        trace_messages.append(
                            {"role": "verdict", "content": verifier_verdict}
                        )
                    if result == "retry":
                        # 需重写：清空当前累积，重写轮会产出全新完整回复（不能拼接）
                        pending_reply = ""
                        yield f"data: {json.dumps({'rewriting': True}, ensure_ascii=False)}\n\n"
                    elif result == "pass":
                        # 验证通过（含未重写直接通过）：推送完整最终版文本，
                        # 前端替换占位/空气泡后打字机渲染
                        full_response = pending_reply
                        yield f"data: {json.dumps({'final': full_response}, ensure_ascii=False)}\n\n"
                    elif result == "fail":
                        # 多次重写仍不准：返回固定文案，避免无限循环拖垮响应
                        full_response = REPLY_ON_VERIFY_FAILED
                        yield f"data: {json.dumps({'final': full_response}, ensure_ascii=False)}\n\n"

            # 5. 保存 assistant 回复
            assistant_msg = Message(
                conversation_id=conv_id, role="assistant", content=full_response
            )
            await self.msg_repo.create(assistant_msg)

            # 全链路落库（status=ok）
            await self._save_run(conv_id, user_id, model, "ok", trace_messages)
            run_recorded = True
        except Exception as e:
            # 运行异常：已收集到的消息序列仍落库并标记 error，便于开发者排查。
            # 注意此时用户消息已保存（在 try 之前），assistant 消息不保存
            # （没有最终回复），符合预期
            await self._save_run(conv_id, user_id, model, "error", trace_messages, error=str(e))
            run_recorded = True
            raise
        finally:
            # 客户端中途断开（GeneratorExit/CancelledError 是 BaseException，
            # 不会触发上面的 except）时，用户消息已入库但 run 记录缺失：
            # 这里补记一条 error 记录，保持两个集合一致。
            # 落库失败由 _save_run 内部静默吞掉，不干扰生成器关闭流程
            if not run_recorded:
                await self._save_run(conv_id, user_id, model, "error", trace_messages, error="流被中断（客户端断开或取消）")

        # 6. 发送结束标志
        yield "data: [DONE]\n\n"
