from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
import json

from models.database import get_db
from models.conversation import Conversation, ConversationMessage
from models.user import User
from api.auth import get_current_user

router = APIRouter(prefix="/api/conversations", tags=["Conversations"])


class MessageResponse(BaseModel):
    id: int
    role: str
    type: str
    content: str
    results: list[str] | None = None
    model: str | None = None
    task_id: str | None = None
    created_at: str | None = None


class ConversationResponse(BaseModel):
    id: int
    title: str
    messages: list[MessageResponse]
    created_at: str | None = None


class ConversationListItem(BaseModel):
    id: int
    title: str
    type: str  # 'image' | 'voice' | 'video' | 'music'
    thumb: str | None = None
    prompt: str | None = None
    created_at: str | None = None


class CreateConversationRequest(BaseModel):
    title: str = "New Conversation"


class AddMessageRequest(BaseModel):
    role: str
    type: str = "text"
    content: str
    results: str | None = None  # JSON string
    model: str | None = None
    task_id: str | None = None


@router.get("", response_model=list[ConversationListItem])
async def list_conversations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出当前用户的对话历史（用于侧边栏列表）"""
    convs = (
        db.query(Conversation)
        .filter(Conversation.user_id == current_user.id)
        .order_by(Conversation.updated_at.desc())
        .all()
    )
    result = []
    for c in convs:
        first_msg = c.messages[0] if c.messages else None
        thumb = None
        conv_type = "text"
        prompt = c.title
        if first_msg:
            prompt = first_msg.content[:60]
            if first_msg.type in ("image", "voice", "video", "music") and first_msg.results:
                try:
                    results = json.loads(first_msg.results)
                    if isinstance(results, list) and results:
                        thumb = results[0]
                except Exception:
                    pass
            conv_type = first_msg.type if first_msg.type != "text" else "image"
        result.append(
            ConversationListItem(
                id=c.id,
                title=c.title[:50] or "New Conversation",
                type=conv_type,
                thumb=thumb,
                prompt=prompt,
                created_at=c.created_at.isoformat() if c.created_at else None,
            )
        )
    return result


@router.get("/{conv_id}", response_model=ConversationResponse)
async def get_conversation(
    conv_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取完整对话内容（用于恢复对话界面）"""
    conv = (
        db.query(Conversation)
        .filter(Conversation.id == conv_id, Conversation.user_id == current_user.id)
        .first()
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages = []
    for m in conv.messages:
        try:
            results = json.loads(m.results) if m.results else None
        except Exception:
            results = None
        messages.append(
            MessageResponse(
                id=m.id,
                role=m.role,
                type=m.type,
                content=m.content,
                results=results,
                model=m.model,
                task_id=m.task_id,
                created_at=m.created_at.isoformat() if m.created_at else None,
            )
        )

    return ConversationResponse(
        id=conv.id,
        title=conv.title,
        messages=messages,
        created_at=conv.created_at.isoformat() if conv.created_at else None,
    )


@router.post("", response_model=ConversationResponse)
async def create_conversation(
    req: CreateConversationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建新对话"""
    conv = Conversation(
        title=req.title,
        user_id=current_user.id,
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return ConversationResponse(
        id=conv.id,
        title=conv.title,
        messages=[],
        created_at=conv.created_at.isoformat() if conv.created_at else None,
    )


@router.patch("/{conv_id}")
async def update_conversation(
    conv_id: int,
    req: CreateConversationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新对话标题"""
    conv = (
        db.query(Conversation)
        .filter(Conversation.id == conv_id, Conversation.user_id == current_user.id)
        .first()
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    conv.title = req.title
    db.commit()
    return {"ok": True}


@router.post("/{conv_id}/messages")
async def add_message(
    conv_id: int,
    req: AddMessageRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """追加消息到对话"""
    conv = (
        db.query(Conversation)
        .filter(Conversation.id == conv_id, Conversation.user_id == current_user.id)
        .first()
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    msg = ConversationMessage(
        conversation_id=conv_id,
        role=req.role,
        type=req.type,
        content=req.content,
        results=req.results,
        model=req.model,
        task_id=req.task_id,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return {"id": msg.id}


@router.delete("/{conv_id}")
async def delete_conversation(
    conv_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除对话"""
    conv = (
        db.query(Conversation)
        .filter(Conversation.id == conv_id, Conversation.user_id == current_user.id)
        .first()
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    db.delete(conv)
    db.commit()
    return {"ok": True}