from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.middleware.mongodb import get_db
from app.dependencies import get_current_user_id
from app.services.chat_service import ChatService
from pydantic import BaseModel


# 聊天模块路由，统一前缀 /chat
router = APIRouter(prefix="/chat", tags=["chat"])


class SendMessageRequest(BaseModel):
    """发送消息请求体"""
    content: str


# POST /chat/conversations — 创建新对话
@router.post("/conversations", status_code=201)
async def create_conversation(
    user_id: str = Depends(get_current_user_id),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = ChatService(db)
    return await service.create_conversation(user_id)


# GET /chat/conversations — 获取对话列表
@router.get("/conversations")
async def list_conversations(
    user_id: str = Depends(get_current_user_id),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = ChatService(db)
    return await service.list_conversations(user_id)


# DELETE /chat/conversations/{conv_id} — 删除对话
@router.delete("/conversations/{conv_id}")
async def delete_conversation(
    conv_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = ChatService(db)
    await service.delete_conversation(conv_id, user_id)
    return {"detail": "deleted"}


# GET /chat/conversations/{conv_id}/messages — 获取历史消息
@router.get("/conversations/{conv_id}/messages")
async def get_messages(
    conv_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = ChatService(db)
    return await service.get_messages(conv_id, user_id)


# POST /chat/conversations/{conv_id}/messages — 发送消息 & SSE 流式回复
@router.post("/conversations/{conv_id}/messages")
async def send_message(
    conv_id: str,
    body: SendMessageRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = ChatService(db)
    return StreamingResponse(
        service.chat_stream(conv_id, user_id, body.content),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
