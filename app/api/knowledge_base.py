from __future__ import annotations

from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.deps import get_current_user, require_permission
from app.models import Category, Conversation, ConversationFavorite, Document, EvaluationResult, KnowledgeBase, Message, QaLog, User
from app.schemas import KnowledgeBaseCreate, KnowledgeBaseOut, KnowledgeBaseUpdate
from app.services.document_service import delete_document_data
from app.services.ops_service import log_audit
from app.services.vector_store import vector_store

router = APIRouter(prefix="/knowledge-bases", tags=["knowledge-bases"])

@router.get("", response_model=List[KnowledgeBaseOut])
def list_knowledge_bases(db: Session = Depends(get_db), current_user: User = Depends(require_permission("knowledge_base:read"))):
    return db.query(KnowledgeBase).filter_by(user_id=current_user.id, deleted_at=None).order_by(KnowledgeBase.id.desc()).all()


@router.post("", response_model=KnowledgeBaseOut)
def create_knowledge_base(
    payload: KnowledgeBaseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("knowledge_base:create")),
):
    kb = KnowledgeBase(
        user_id=current_user.id,
        name=payload.name,
        description=payload.description,
        embedding_model=settings.embedding_model,
        vector_store_type="chroma",
    )
    db.add(kb)
    db.commit()
    db.refresh(kb)
    return kb


@router.put("/{knowledge_base_id}", response_model=KnowledgeBaseOut)
def update_knowledge_base(
    knowledge_base_id: int,
    payload: KnowledgeBaseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("knowledge_base:update")),
):
    kb = db.query(KnowledgeBase).filter_by(id=knowledge_base_id, user_id=current_user.id, deleted_at=None).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    if payload.name is not None:
        kb.name = payload.name
    if payload.description is not None:
        kb.description = payload.description
    db.commit()
    db.refresh(kb)
    return kb


@router.delete("/{knowledge_base_id}")
def delete_knowledge_base(
    knowledge_base_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("knowledge_base:delete")),
):
    kb = db.query(KnowledgeBase).filter_by(id=knowledge_base_id, user_id=current_user.id, deleted_at=None).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    now = datetime.utcnow()
    kb.deleted_at = now
    db.query(Document).filter_by(user_id=current_user.id, knowledge_base_id=knowledge_base_id).update({"deleted_at": now, "status": "deleted"})
    db.query(Category).filter_by(user_id=current_user.id, knowledge_base_id=knowledge_base_id).update({"deleted_at": now})
    log_audit(db, current_user, "knowledge_base.soft_delete", "knowledge_base", kb.id, {"name": kb.name})
    db.commit()
    return {"ok": True}
