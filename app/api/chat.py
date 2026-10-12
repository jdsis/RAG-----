from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, get_db
from app.deps import ensure_user_knowledge_base, get_current_user, require_permission
from app.models import Conversation, ConversationFavorite, Message, User
from app.schemas import ChatRequest, ConversationOut, MessageOut
from app.services.rag_service import answer_stream

router = APIRouter(tags=["chat"])


def _sse_data(value: str) -> str:
    lines = str(value).splitlines()
    if not lines:
        return "data: \n\n"
    return "".join(f"data: {line}\n" for line in lines) + "\n"


@router.post("/chat/stream")
def chat_stream(
    payload: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("chat:ask")),
):
    ensure_user_knowledge_base(db, current_user, payload.knowledge_base_id)

    def events():
        db = SessionLocal()
        try:
            user = db.get(User, current_user.id)
            for item in answer_stream(db, user, payload):
                if item.startswith("event:"):
                    yield item
                else:
                    yield _sse_data(item)
        finally:
            db.close()

    return StreamingResponse(events(), media_type="text/event-stream")


@router.get("/conversations", response_model=List[ConversationOut])
def list_conversations(db: Session = Depends(get_db), current_user: User = Depends(require_permission("chat:read"))):
    return db.query(Conversation).filter_by(user_id=current_user.id).order_by(Conversation.id.desc()).all()


@router.get("/favorites")
def list_favorites(db: Session = Depends(get_db), current_user: User = Depends(require_permission("chat:read"))):
    rows = (
        db.query(ConversationFavorite, Conversation)
        .join(Conversation, Conversation.id == ConversationFavorite.conversation_id)
        .filter(ConversationFavorite.user_id == current_user.id, Conversation.user_id == current_user.id)
        .order_by(ConversationFavorite.id.desc())
        .all()
    )
    return [
        {
            "id": conversation.id,
            "knowledge_base_id": conversation.knowledge_base_id,
            "category_id": conversation.category_id,
            "title": conversation.title,
            "created_at": conversation.created_at,
            "favorited_at": favorite.created_at,
        }
        for favorite, conversation in rows
    ]


@router.post("/favorites/{conversation_id}")
def add_favorite(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("chat:favorite")),
):
    conversation = db.query(Conversation).filter_by(id=conversation_id, user_id=current_user.id).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    favorite = db.query(ConversationFavorite).filter_by(user_id=current_user.id, conversation_id=conversation_id).first()
    if not favorite:
        db.add(ConversationFavorite(user_id=current_user.id, conversation_id=conversation_id))
        db.commit()
    return {"ok": True}


@router.delete("/favorites/{conversation_id}")
def remove_favorite(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("chat:favorite")),
):
    db.query(ConversationFavorite).filter_by(user_id=current_user.id, conversation_id=conversation_id).delete()
    db.commit()
    return {"ok": True}


@router.get("/conversations/{conversation_id}/messages", response_model=List[MessageOut])
def list_messages(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("chat:read")),
):
    return (
        db.query(Message)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .filter(Message.user_id == current_user.id, Conversation.id == conversation_id)
        .order_by(Message.id)
        .all()
    )
