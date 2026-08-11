from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.middleware.mongodb import get_db
from app.services.chat_service import ChatService
from app.schemas.chat import (
    SendMessageRequest,
    ConversationResponse,
    ConversationListItem,
    MessageResponse,
    DeleteResponse,
)


# 聊天模块路由，统一前缀 /chat
router = APIRouter(prefix="/chat", tags=["chat"])


# POST /chat/conversations — 创建新对话（无需登录）
@router.post("/conversations", status_code=201, response_model=ConversationResponse)
async def create_conversation(
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = ChatService(db)
    return await service.create_conversation()


# GET /chat/conversations — 获取对话列表（无需登录）
@router.get("/conversations", response_model=list[ConversationListItem])
async def list_conversations(
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = ChatService(db)
    return await service.list_conversations()


# DELETE /chat/conversations/{conv_id} — 删除对话（无需登录）
@router.delete("/conversations/{conv_id}", response_model=DeleteResponse)
async def delete_conversation(
    conv_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = ChatService(db)
    await service.delete_conversation(conv_id)
    return DeleteResponse()


# GET /chat/conversations/{conv_id}/messages — 获取历史消息（无需登录）
@router.get("/conversations/{conv_id}/messages", response_model=list[MessageResponse])
async def get_messages(
    conv_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = ChatService(db)
    return await service.get_messages(conv_id)


# POST /chat/conversations/{conv_id}/messages — 发送消息 & SSE 流式回复（无需登录）
@router.post("/conversations/{conv_id}/messages")
async def send_message(
    conv_id: str,
    body: SendMessageRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = ChatService(db)
    return StreamingResponse(
        service.chat_stream(conv_id, body.content, body.model),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
