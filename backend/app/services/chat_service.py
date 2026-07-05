import asyncio
import json
import warnings
from datetime import datetime, timezone

# 智谱 SDK 内部用 API Key 的 secret 部分签 JWT，密钥长度不受我们控制，屏蔽无害警告
warnings.filterwarnings("ignore", category=UserWarning, module="jwt")

from langchain_core.messages import HumanMessage, AIMessage
from langchain_community.chat_models import ChatZhipuAI
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config.settings import settings
from app.repositories.conversation_repo import ConversationRepo
from app.repositories.message_repo import MessageRepo
from app.models.message import Message


class ChatService:
    """聊天业务层：串联 MongoDB 数据存取和 LangChain LLM 调用"""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.conv_repo = ConversationRepo(db)
        self.msg_repo = MessageRepo(db)

    # ----------------------------------------------------------------
    # 对话管理
    # ----------------------------------------------------------------

    async def create_conversation(self, user_id: str) -> dict:
        """创建新对话，返回对话基本信息"""
        conv = await self.conv_repo.create(user_id)
        return {"id": conv.id, "title": conv.title, "created_at": conv.created_at}

    async def list_conversations(self, user_id: str) -> list[dict]:
        """列出用户的所有对话"""
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

    async def delete_conversation(self, conv_id: str, user_id: str):
        """删除对话及其全部消息"""
        conv = await self.conv_repo.get_by_id(conv_id)
        if not conv or conv.user_id != user_id:
            raise PermissionError("对话不存在或无权访问")
        await self.msg_repo.delete_by_conversation(conv_id)
        await self.conv_repo.delete(conv_id)

    async def get_messages(self, conv_id: str, user_id: str) -> list[dict]:
        """获取对话的历史消息"""
        conv = await self.conv_repo.get_by_id(conv_id)
        if not conv or conv.user_id != user_id:
            raise PermissionError("对话不存在或无权访问")
        msgs = await self.msg_repo.list_by_conversation(conv_id)
        return [
            {"role": m.role, "content": m.content, "created_at": m.created_at}
            for m in msgs
        ]

    # ----------------------------------------------------------------
    # LLM 流式聊天
    # ----------------------------------------------------------------

    async def chat_stream(self, conv_id: str, user_id: str, content: str):
        """
        核心流程：
        1. 校验对话归属
        2. 保存用户消息
        3. 拉取完整历史
        4. 调用 LangChain astream 逐块产出
        5. 流结束后保存 assistant 消息
        6. 如果是首条消息，后台异步生成标题
        """
        # 1. 校验对话归属
        conv = await self.conv_repo.get_by_id(conv_id)
        if not conv or conv.user_id != user_id:
            raise PermissionError("对话不存在或无权访问")

        # 2. 保存用户消息
        user_msg = Message(conversation_id=conv_id, role="user", content=content)
        await self.msg_repo.create(user_msg)

        # 3. 拉取历史消息（含刚保存的用户消息）
        history = await self.msg_repo.list_by_conversation(conv_id)
        langchain_messages = []
        for m in history:
            if m.role == "user":
                langchain_messages.append(HumanMessage(content=m.content))
            elif m.role == "assistant":
                langchain_messages.append(AIMessage(content=m.content))

        # 4. 调用 LangChain 流式生成
        llm = ChatZhipuAI(
            model=settings.LLM_MODEL,
            api_key=settings.ZHIPUAI_API_KEY,
            streaming=True,
        )

        full_response = ""
        async for chunk in llm.astream(langchain_messages):
            if chunk.content:
                token = chunk.content
                full_response += token
                yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"

        # 5. 保存 assistant 回复
        assistant_msg = Message(
            conversation_id=conv_id, role="assistant", content=full_response
        )
        await self.msg_repo.create(assistant_msg)

        # 6. 发送结束标志
        yield "data: [DONE]\n\n"

        # 7. 如果是首条完整对话（恰好 2 条消息），后台生成标题
        if len(history) == 1:  # 只有刚才插入的那条 user 消息
            asyncio.create_task(self._generate_title(conv_id))

    async def _generate_title(self, conv_id: str):
        """后台异步生成对话标题，基于首条 user 消息和 LLM 的回复"""
        try:
            history = await self.msg_repo.list_by_conversation(conv_id)
            messages_text = "\n".join(f"{m.role}: {m.content}" for m in history)

            llm = ChatZhipuAI(
                model=settings.LLM_MODEL,
                api_key=settings.ZHIPUAI_API_KEY,
            )
            title_prompt = (
                f"根据以下对话内容，生成一个简短的对话标题（不超过20个字）：\n\n{messages_text}"
            )
            result = await llm.ainvoke([HumanMessage(content=title_prompt)])
            title = result.content.strip().strip('"\'')
            await self.conv_repo.update_title(conv_id, title)
        except Exception as e:
            # 标题生成失败不影响正常聊天，静默处理
            print(f"Title generation failed: {e}")
