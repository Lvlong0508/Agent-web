import json

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config.settings import settings
from app.repositories.conversation_repo import ConversationRepo
from app.repositories.message_repo import MessageRepo
from app.models.message import Message
from app.services.agent_graph import build_agent_graph
from app.services.prompts import SYSTEM_PROMPT
from app.tools import get_tools


class ChatService:
    """聊天业务层：串联 MongoDB 数据存取和 LangGraph agent 图调用"""

    def __init__(self, db: AsyncIOMotorDatabase, graph=None, session_factory=None):
        self.conv_repo = ConversationRepo(db)
        self.msg_repo = MessageRepo(db)
        # 未显式传入时自动构建 agent 图（测试可注入 mock）；
        # 传入 session_factory 则给图绑定 MySQL 账单工具，让 agent 能调用
        tools = get_tools(session_factory) if session_factory else []
        self.graph = graph or build_agent_graph(self.conv_repo, tools=tools)

    # ----------------------------------------------------------------
    # 对话管理
    # ----------------------------------------------------------------

    async def create_conversation(self) -> dict:
        """创建新对话，返回对话基本信息（归属固定匿名用户）"""
        conv = await self.conv_repo.create(settings.DEFAULT_USER_ID)
        return {"id": conv.id, "title": conv.title, "created_at": conv.created_at}

    async def list_conversations(self) -> list[dict]:
        """列出全部对话（单用户模式下即匿名用户的全部对话）"""
        convs = await self.conv_repo.list_by_user(settings.DEFAULT_USER_ID)
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
        """删除对话及其全部消息"""
        conv = await self.conv_repo.get_by_id(conv_id)
        if not conv or conv.user_id != settings.DEFAULT_USER_ID:
            raise PermissionError("对话不存在或无权访问")
        await self.msg_repo.delete_by_conversation(conv_id)
        await self.conv_repo.delete(conv_id)

    async def get_messages(self, conv_id: str) -> list[dict]:
        """获取对话的历史消息"""
        conv = await self.conv_repo.get_by_id(conv_id)
        if not conv or conv.user_id != settings.DEFAULT_USER_ID:
            raise PermissionError("对话不存在或无权访问")
        msgs = await self.msg_repo.list_by_conversation(conv_id)
        return [
            {"role": m.role, "content": m.content, "created_at": m.created_at}
            for m in msgs
        ]

    # ----------------------------------------------------------------
    # Agent 图驱动聊天
    # ----------------------------------------------------------------

    async def chat_stream(self, conv_id: str, content: str, model: str, thinking: bool = False):
        """
        核心流程：
        1. 校验对话归属（匿名用户）
        2. 保存用户消息
        3. 拉取完整历史
        4. 运行 LangGraph agent 图（generate_title → agent），流式产出 token
        5. 流结束后保存 assistant 消息

        thinking：是否开启深度思考（仅通义千问生效），透传给 agent 节点
        """
        # 1. 校验对话归属
        conv = await self.conv_repo.get_by_id(conv_id)
        if not conv or conv.user_id != settings.DEFAULT_USER_ID:
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
        full_response = "" # 存储返回值
        async for mode, data in self.graph.astream(
            {
                "messages": langchain_messages,
                "conv_id": conv_id,
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
                token = chunk.content if isinstance(chunk.content, str) else ""
                if token:
                    full_response += token
                    yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"
            elif mode == "updates":
                # data 形如 {"generate_title": {"generated_title": "标题"}}；
                # 仅在标题节点真生成了标题时（非空）推送事件，避免无谓消息
                title = data.get("generate_title", {}).get("generated_title")
                if title:
                    yield f"data: {json.dumps({'title': title}, ensure_ascii=False)}\n\n"

        # 5. 保存 assistant 回复
        assistant_msg = Message(
            conversation_id=conv_id, role="assistant", content=full_response
        )
        await self.msg_repo.create(assistant_msg)

        # 6. 发送结束标志
        yield "data: [DONE]\n\n"
