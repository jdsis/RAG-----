from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import Category, Document, DocumentChunk, User
from app.services.document_classifier import classify_document
from app.services.document_loader import load_document, load_web_page
from app.services.ollama_service import embed_texts
from app.services.text_splitter import split_text
from app.services.upload_utils import safe_unique_filename
from app.services.vector_store import vector_store


def find_category(db: Session, user_id: int, knowledge_base_id: int, name: str) -> Optional[Category]:
    return (
        db.query(Category)
        .filter(
            Category.user_id == user_id,
            Category.knowledge_base_id == knowledge_base_id,
            func.lower(Category.name) == name.lower(),
        )
        .first()
    )


def uncategorized_category(db: Session, user_id: int, knowledge_base_id: int) -> Optional[Category]:
    return find_category(db, user_id, knowledge_base_id, "未分类")


def get_or_create_category(db: Session, user_id: int, knowledge_base_id: int, name: str) -> Optional[Category]:
    if not name or name == "未分类":
        return None
    category = find_category(db, user_id, knowledge_base_id, name)
    if category:
        return category
    category = Category(
        user_id=user_id,
        knowledge_base_id=knowledge_base_id,
        name=name,
        description="系统根据文档内容自动创建",
    )
    db.add(category)
    db.flush()
    return category


def assign_document_category(
    db: Session,
    document: Document,
    category: Optional[Category],
    classify_status: str = "manual",
    confidence: Optional[float] = None,
    reason: Optional[str] = None,
) -> None:
    document.category_id = category.id if category else None
    document.category_name = category.name if category else None
    document.classify_status = classify_status
    if confidence is not None:
        document.classify_confidence = confidence
    if reason is not None:
        document.classify_reason = reason
    db.query(DocumentChunk).filter_by(document_id=document.id, user_id=document.user_id).update(
        {"category_id": document.category_id, "category_name": document.category_name}
    )
    ids = [
        row[0]
        for row in db.query(DocumentChunk.vector_id)
        .filter_by(document_id=document.id, user_id=document.user_id)
        .all()
    ]
    vector_store.update_category_metadata(ids, document.category_id, document.category_name)


def reclassify_document(db: Session, document: Document) -> None:
    pages = _load_pages(document)
    full_text = "\n".join(text for _, text in pages)
    category_name, confidence, reason = classify_document(document.filename, full_text)
    category = get_or_create_category(db, document.user_id, document.knowledge_base_id, category_name)
    assign_document_category(db, document, category, "auto", confidence, reason)


def process_document(db: Session, document: Document, auto_classify: bool = True) -> None:
    document.status = "parsing"
    document.error_message = None
    db.flush()

    pages = _load_pages(document)
    full_text = "\n".join(text for _, text in pages)
    if auto_classify:
        category_name, confidence, reason = classify_document(document.filename, full_text)
    else:
        category_name, confidence, reason = "未分类", 0.0, "未启用自动分类"
    category = get_or_create_category(db, document.user_id, document.knowledge_base_id, category_name)
    document.category_id = category.id if category else None
    document.category_name = category.name if category else None
    document.classify_status = "auto" if auto_classify else "none"
    document.classify_confidence = confidence
    document.classify_reason = reason
    document.status = "embedding"
    db.flush()

    _delete_chunks(db, document)
    pending_chunks = _split_pages(pages)
    user = db.get(User, document.user_id)
    embeddings: List[List[float]] = []
    batch_size = 16
    for start in range(0, len(pending_chunks), batch_size):
        batch = [chunk_text for _, chunk_text in pending_chunks[start : start + batch_size]]
        embeddings.extend(embed_texts(batch, user=user))

    ids: List[str] = []
    documents: List[str] = []
    metadatas: List[dict] = []
    for chunk_index, (page_number, chunk_text) in enumerate(pending_chunks):
        vector_id = f"doc_{document.id}_chunk_{chunk_index}"
        embedding = embeddings[chunk_index] if chunk_index < len(embeddings) else []
        chunk = DocumentChunk(
            user_id=document.user_id,
            knowledge_base_id=document.knowledge_base_id,
            category_id=document.category_id,
            category_name=document.category_name,
            document_id=document.id,
            vector_id=vector_id,
            chunk_index=chunk_index,
            content=chunk_text,
            embedding_json=json.dumps(embedding) if embedding else None,
            page_number=page_number,
            source_name=document.filename,
        )
        db.add(chunk)
        if embedding:
            ids.append(vector_id)
            documents.append(chunk_text)
            metadatas.append(
                {
                    "user_id": document.user_id,
                    "knowledge_base_id": document.knowledge_base_id,
                    "category_id": document.category_id or 0,
                    "category_name": document.category_name or "",
                    "document_id": document.id,
                    "document_name": document.filename,
                    "page_number": page_number or 0,
                    "chunk_index": chunk_index,
                }
            )

    if ids:
        vector_store.upsert_chunks(
            ids=ids,
            documents=documents,
            embeddings=[embeddings[index] for index in range(len(ids))],
            metadatas=metadatas,
        )
    document.chunk_count = len(pending_chunks)
    document.status = "completed"


def create_web_document(db: Session, user: User, knowledge_base_id: int, url: str, upload_dir: Path) -> Document:
    title, content = load_web_page(url)
    target = upload_dir / safe_unique_filename(f"{title}.txt", "web_page")
    upload_dir.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return Document(
        user_id=user.id,
        knowledge_base_id=knowledge_base_id,
        filename=title,
        file_type="url",
        file_path=str(target),
        file_size=target.stat().st_size,
        status="pending",
    )


def delete_document_data(db: Session, document: Document, remove_file: bool = False) -> None:
    _delete_chunks(db, document)
    if remove_file:
        try:
            Path(document.file_path).unlink(missing_ok=True)
        except OSError:
            pass
    db.delete(document)


def _delete_chunks(db: Session, document: Document) -> None:
    vector_store.delete_document(document.id, document.user_id)
    db.query(DocumentChunk).filter_by(document_id=document.id, user_id=document.user_id).delete()


def _load_pages(document: Document) -> List[Tuple[Optional[int], str]]:
    return load_document(Path(document.file_path))


def _split_pages(pages: List[Tuple[Optional[int], str]]) -> List[Tuple[Optional[int], str]]:
    pending = []
    for page_number, text in pages:
        for chunk_text in split_text(text):
            pending.append((page_number, chunk_text))
    return pending
