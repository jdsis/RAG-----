from __future__ import annotations

from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.deps import ensure_user_knowledge_base, get_current_user, require_permission
from app.models import Category, Document, DocumentChunk, KnowledgeBase, User
from app.schemas import CategoryCreate, CategoryOut, CategoryUpdate
from app.services.document_service import assign_document_category
from app.services.vector_store import vector_store

router = APIRouter(prefix="/categories", tags=["categories"])

LEGACY_DEFAULT_CATEGORY_NAMES = {
    "Java",
    "Python",
    "前端",
    "嵌入式",
    "数据库",
    "人工智能",
    "操作系统",
    "计算机网络",
    "大数据",
    "软件工程",
    "算法与数据结构",
    "未分类",
}


@router.get("", response_model=List[CategoryOut])
def list_categories(
    knowledge_base_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("category:read")),
):
    ensure_user_knowledge_base(db, current_user, knowledge_base_id)
    return db.query(Category).filter_by(user_id=current_user.id, knowledge_base_id=knowledge_base_id, deleted_at=None).all()


@router.post("", response_model=CategoryOut)
def create_category(
    payload: CategoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("category:create")),
):
    kb = db.query(KnowledgeBase).filter_by(id=payload.knowledge_base_id, user_id=current_user.id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    category = Category(user_id=current_user.id, **payload.model_dump())
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


@router.post("/cleanup-empty-defaults")
def cleanup_empty_default_categories(
    knowledge_base_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("category:delete")),
):
    ensure_user_knowledge_base(db, current_user, knowledge_base_id)
    removed = 0
    categories = (
        db.query(Category)
        .filter(Category.user_id == current_user.id, Category.knowledge_base_id == knowledge_base_id, Category.deleted_at.is_(None))
        .all()
    )
    for category in categories:
        if category.name not in LEGACY_DEFAULT_CATEGORY_NAMES:
            continue
        has_document = (
            db.query(Document.id)
            .filter(Document.user_id == current_user.id, Document.category_id == category.id)
            .first()
        )
        if has_document:
            continue
        db.delete(category)
        removed += 1
    db.commit()
    return {"ok": True, "removed": removed}


@router.put("/{category_id}", response_model=CategoryOut)
def update_category(
    category_id: int,
    payload: CategoryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("category:update")),
):
    category = db.query(Category).filter_by(id=category_id, user_id=current_user.id, deleted_at=None).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    old_name = category.name
    if payload.name is not None:
        category.name = payload.name
    if payload.description is not None:
        category.description = payload.description
    if payload.parent_id is not None:
        parent = db.query(Category).filter_by(
            id=payload.parent_id,
            user_id=current_user.id,
            knowledge_base_id=category.knowledge_base_id,
        ).first()
        if not parent:
            raise HTTPException(status_code=404, detail="Parent category not found")
        category.parent_id = payload.parent_id
    if payload.name is not None and payload.name != old_name:
        db.query(Document).filter_by(user_id=current_user.id, category_id=category.id).update(
            {"category_name": category.name}
        )
        db.query(DocumentChunk).filter_by(user_id=current_user.id, category_id=category.id).update(
            {"category_name": category.name}
        )
        ids = [
            row[0]
            for row in db.query(DocumentChunk.vector_id)
            .filter_by(user_id=current_user.id, category_id=category.id)
            .all()
        ]
        vector_store.update_category_metadata(ids, category.id, category.name)
    db.commit()
    db.refresh(category)
    return category


@router.delete("/{category_id}")
def delete_category(
    category_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("category:delete")),
):
    category = db.query(Category).filter_by(id=category_id, user_id=current_user.id, deleted_at=None).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    for document in db.query(Document).filter_by(user_id=current_user.id, category_id=category.id).all():
        assign_document_category(db, document, None, classify_status="manual", confidence=0, reason="原分类已删除，转为未分类")
    db.query(Category).filter_by(parent_id=category.id, user_id=current_user.id).update({"parent_id": None})
    category.deleted_at = datetime.utcnow()
    db.commit()
    return {"ok": True}
