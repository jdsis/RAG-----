from __future__ import annotations

import logging
import os
import re
import secrets
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path
from string import ascii_lowercase, ascii_uppercase, digits
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import hash_password
from app.deps import require_admin
from app.api.document import _preview_from_file, _resolve_document_path, _text_blocks_from_plain_text
from app.models import (
    Category,
    Conversation,
    ConversationFavorite,
    ConfigChangeHistory,
    Document,
    DocumentChunk,
    EvaluationResult,
    KnowledgeBase,
    Message,
    QaLog,
    User,
)
from app.schemas import (
    AdminCategoryOut,
    AdminDocumentOut,
    AdminKnowledgeBaseOut,
    AdminPasswordInviteOut,
    AdminSettingsOut,
    AdminSettingsUpdate,
    AdminUserCreate,
    AdminUserUpdate,
    CategoryUpdate,
    DocumentOut,
    EvaluationResultOut,
    KnowledgeBaseUpdate,
    QaLogOut,
    UserOut,
)
from app.services.document_service import (
    assign_document_category,
    delete_document_data,
    reclassify_document,
    uncategorized_category,
)
from app.services.upload_utils import safe_unique_filename, save_upload_file
from app.services.vector_store import vector_store
from app.services.ops_service import log_audit
from app.services.task_worker import enqueue_parse_task

router = APIRouter(prefix="/admin", tags=["admin"])

SUPPORTED_DOCUMENT_SUFFIXES = {".pdf", ".txt", ".md", ".docx", ".doc", ".xlsx", ".xls", ".csv", ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
PREVIEW_CHUNK_LIMIT = 80
SYSTEM_LOG_BUFFER = deque(maxlen=200)
ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")
ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
SETTING_ENV_MAP = {
    "app_name": "APP_NAME",
    "database_url": "DATABASE_URL",
    "upload_dir": "UPLOAD_DIR",
    "jwt_secret_key": "JWT_SECRET_KEY",
    "jwt_expire_minutes": "JWT_EXPIRE_MINUTES",
    "ollama_base_url": "OLLAMA_BASE_URL",
    "chat_model": "CHAT_MODEL",
    "embedding_model": "EMBEDDING_MODEL",
    "ollama_timeout_seconds": "OLLAMA_TIMEOUT_SECONDS",
    "chroma_dir": "CHROMA_DIR",
    "chunk_size": "CHUNK_SIZE",
    "chunk_overlap": "CHUNK_OVERLAP",
    "top_k": "TOP_K",
}
RESTART_REQUIRED_SETTING_KEYS = ["database_url", "chroma_dir"]


class AdminSystemLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            SYSTEM_LOG_BUFFER.append(
                {
                    "source": "backend",
                    "level": record.levelname,
                    "time": datetime.fromtimestamp(record.created).isoformat(timespec="seconds"),
                    "message": self.format(record),
                }
            )
        except Exception:
            return


def _ensure_system_log_handler() -> None:
    root = logging.getLogger()
    if any(getattr(handler, "_admin_system_log_handler", False) for handler in root.handlers):
        return
    handler = AdminSystemLogHandler()
    handler._admin_system_log_handler = True
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
    root.addHandler(handler)


_ensure_system_log_handler()


@router.get("/users", response_model=List[UserOut])
def list_users(
    role: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    query = db.query(User)
    if role:
        query = query.filter(User.role == role)
    if status:
        query = query.filter(User.status == status)
    return query.order_by(User.id.desc()).all()


@router.get("/system-logs")
def list_system_logs(
    limit: int = 80,
    _: User = Depends(require_admin),
):
    max_items = max(1, min(limit, 200))
    logs = list(SYSTEM_LOG_BUFFER)[-max_items:]
    logs.extend(_read_known_log_files(max_items))
    return sorted(logs, key=lambda item: item.get("time") or "", reverse=True)[:max_items]


@router.get("/settings", response_model=AdminSettingsOut)
def get_system_settings(_: User = Depends(require_admin)):
    return _settings_out()


@router.put("/settings", response_model=AdminSettingsOut)
def update_system_settings(
    payload: AdminSettingsUpdate,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    data = payload.model_dump(exclude_unset=True, exclude_none=True)
    _normalize_settings_update(data)
    if "jwt_secret_key" in data and not data["jwt_secret_key"]:
        data.pop("jwt_secret_key")
    _validate_settings_update(data)
    if data:
        old_values = {key: getattr(settings, key) for key in data}
        _write_env_values({SETTING_ENV_MAP[key]: value for key, value in data.items()})
        for key, value in data.items():
            os.environ[SETTING_ENV_MAP[key]] = str(value)
            setattr(settings, key, value)
            if key == "jwt_secret_key":
                settings.jwt_secret_configured = True
            db.add(
                ConfigChangeHistory(
                    user_id=current_admin.id,
                    key=key,
                    old_value=str(old_values.get(key)),
                    new_value=str(value),
                )
            )
        log_audit(db, current_admin, "settings.update", "settings", None, data)
        db.commit()
    return _settings_out()


def _settings_out() -> AdminSettingsOut:
    return AdminSettingsOut(
        app_name=settings.app_name,
        database_url=settings.database_url,
        upload_dir=settings.upload_dir,
        jwt_expire_minutes=settings.jwt_expire_minutes,
        jwt_secret_configured=settings.jwt_secret_configured,
        ollama_base_url=settings.ollama_base_url,
        chat_model=settings.chat_model,
        embedding_model=settings.embedding_model,
        ollama_timeout_seconds=settings.ollama_timeout_seconds,
        chroma_dir=settings.chroma_dir,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        top_k=settings.top_k,
        restart_required_keys=RESTART_REQUIRED_SETTING_KEYS,
    )


def _validate_settings_update(data: dict[str, Any]) -> None:
    positive_ints = ["jwt_expire_minutes", "ollama_timeout_seconds", "chunk_size", "top_k"]
    non_negative_ints = ["chunk_overlap"]
    for key in positive_ints:
        if key in data and int(data[key]) <= 0:
            raise HTTPException(status_code=400, detail=f"{key} must be greater than 0")
    for key in non_negative_ints:
        if key in data and int(data[key]) < 0:
            raise HTTPException(status_code=400, detail=f"{key} must be greater than or equal to 0")
    if "chunk_size" in data and "chunk_overlap" in data and int(data["chunk_overlap"]) >= int(data["chunk_size"]):
        raise HTTPException(status_code=400, detail="chunk_overlap must be smaller than chunk_size")
    for key in ["app_name", "database_url", "upload_dir", "ollama_base_url", "chat_model", "embedding_model", "chroma_dir"]:
        if key in data and not str(data[key]).strip():
            raise HTTPException(status_code=400, detail=f"{key} cannot be empty")


def _normalize_settings_update(data: dict[str, Any]) -> None:
    text_keys = [
        "app_name",
        "database_url",
        "upload_dir",
        "jwt_secret_key",
        "ollama_base_url",
        "chat_model",
        "embedding_model",
        "chroma_dir",
    ]
    for key in text_keys:
        if key in data and data[key] is not None:
            data[key] = str(data[key]).strip()


def _write_env_values(values: dict[str, Any]) -> None:
    existing: dict[str, str] = {}
    order: list[str] = []
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            if "=" not in line or line.strip().startswith("#"):
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            existing[key] = value.strip()
            order.append(key)
    for key, value in values.items():
        existing[key] = str(value)
        if key not in order:
            order.append(key)
    ENV_PATH.write_text("\n".join(f"{key}={existing[key]}" for key in order) + "\n", encoding="utf-8")


def _read_known_log_files(limit: int) -> list[dict]:
    entries: list[dict] = []
    frontend_log_dir = os.getenv("FRONTEND_LOG_DIR")
    candidate_dirs = [Path(frontend_log_dir)] if frontend_log_dir else []
    candidate_dirs.extend([
        Path("F:/uni/data"),
        Path.cwd() / "logs",
        Path.cwd().parent / "data",
    ])
    seen: set[Path] = set()
    for directory in candidate_dirs:
        if not directory.exists() or not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.log"), key=lambda item: item.stat().st_mtime, reverse=True)[:8]:
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            source = "frontend" if path.name.startswith("vite-") else "backend"
            entries.extend(_tail_log_file(path, source, limit))
    return entries[-limit:]


def _tail_log_file(path: Path, source: str, limit: int) -> list[dict]:
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()[-limit:]
    except OSError:
        return []
    timestamp = datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")
    entries = []
    for line in lines:
        message = ANSI_ESCAPE_RE.sub("", line).strip()
        if not message:
            continue
        entries.append({
            "source": source,
            "level": "INFO",
            "time": timestamp,
            "message": f"{path.name}: {message}",
        })
    return entries


@router.post("/users", response_model=UserOut)
def create_user(
    payload: AdminUserCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    if payload.role not in {"user", "admin"}:
        raise HTTPException(status_code=400, detail="Invalid role")
    if payload.status not in {"active", "disabled"}:
        raise HTTPException(status_code=400, detail="Invalid status")
    if db.query(User).filter_by(username=payload.username).first():
        raise HTTPException(status_code=400, detail="Username already exists")
    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        role=payload.role,
        status=payload.status,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.put("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: AdminUserUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if payload.username is not None:
        exists = db.query(User).filter(User.username == payload.username, User.id != user_id).first()
        if exists:
            raise HTTPException(status_code=400, detail="Username already exists")
        user.username = payload.username
    if payload.password:
        user.password_hash = hash_password(payload.password)
    if payload.role is not None:
        if payload.role not in {"user", "admin"}:
            raise HTTPException(status_code=400, detail="Invalid role")
        user.role = payload.role
    if payload.status is not None:
        if payload.status not in {"active", "disabled"}:
            raise HTTPException(status_code=400, detail="Invalid status")
        user.status = payload.status
    for field in ["document_quota", "storage_quota_mb", "query_quota", "permissions"]:
        value = getattr(payload, field, None)
        if value is not None:
            setattr(user, field, value)
    log_audit(db, _, "admin.user.update", "user", user.id, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(user)
    return user


@router.post("/users/{user_id}/password-invite", response_model=AdminPasswordInviteOut)
def generate_password_invite(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    alphabet = ascii_lowercase + ascii_uppercase + digits
    code_chars = [
        secrets.choice(ascii_lowercase),
        secrets.choice(ascii_uppercase),
        secrets.choice(digits),
        *(secrets.choice(alphabet) for _ in range(3)),
    ]
    secrets.SystemRandom().shuffle(code_chars)
    code = "".join(code_chars)
    expires_at = datetime.utcnow() + timedelta(minutes=3)
    user.reset_invite_code = code
    user.reset_invite_expires_at = expires_at
    db.commit()
    db.refresh(user)
    return AdminPasswordInviteOut(
        user_id=user.id,
        username=user.username,
        invite_code=code,
        expires_at=expires_at,
    )


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
):
    if current_admin.id == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete current admin user")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    _delete_user_owned_data(db, user_id)
    db.delete(user)
    db.commit()
    return {"ok": True}


@router.get("/knowledge-bases", response_model=List[AdminKnowledgeBaseOut])
def list_knowledge_bases(
    user_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    query = db.query(KnowledgeBase)
    if user_id:
        query = query.filter(KnowledgeBase.user_id == user_id)
    return query.filter(KnowledgeBase.deleted_at.is_(None)).order_by(KnowledgeBase.id.desc()).all()


@router.put("/knowledge-bases/{knowledge_base_id}", response_model=AdminKnowledgeBaseOut)
def update_knowledge_base(
    knowledge_base_id: int,
    payload: KnowledgeBaseUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    kb = db.get(KnowledgeBase, knowledge_base_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    if payload.name is not None:
        kb.name = payload.name
    if payload.description is not None:
        kb.description = payload.description
    db.commit()
    db.refresh(kb)
    return kb


@router.delete("/knowledge-bases/{knowledge_base_id}")
def delete_knowledge_base(
    knowledge_base_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    kb = db.get(KnowledgeBase, knowledge_base_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    kb.deleted_at = datetime.utcnow()
    db.query(Document).filter_by(knowledge_base_id=kb.id).update({"deleted_at": kb.deleted_at, "status": "deleted"})
    db.query(Category).filter_by(knowledge_base_id=kb.id).update({"deleted_at": kb.deleted_at})
    log_audit(db, _, "admin.knowledge_base.soft_delete", "knowledge_base", kb.id, {"name": kb.name})
    db.commit()
    return {"ok": True}


@router.get("/categories", response_model=List[AdminCategoryOut])
def list_categories(
    user_id: Optional[int] = None,
    knowledge_base_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    query = db.query(Category)
    if user_id:
        query = query.filter(Category.user_id == user_id)
    if knowledge_base_id:
        query = query.filter(Category.knowledge_base_id == knowledge_base_id)
    return query.filter(Category.deleted_at.is_(None)).order_by(Category.id.desc()).all()


@router.put("/categories/{category_id}", response_model=AdminCategoryOut)
def update_category(
    category_id: int,
    payload: CategoryUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    category = db.get(Category, category_id)
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
            user_id=category.user_id,
            knowledge_base_id=category.knowledge_base_id,
        ).first()
        if not parent:
            raise HTTPException(status_code=404, detail="Parent category not found")
        category.parent_id = payload.parent_id
    if payload.name is not None and payload.name != old_name:
        db.query(Document).filter_by(user_id=category.user_id, category_id=category.id).update(
            {"category_name": category.name}
        )
        chunk_ids = [
            row[0]
            for row in db.query(DocumentChunk.vector_id)
            .filter_by(user_id=category.user_id, category_id=category.id)
            .all()
        ]
        db.query(DocumentChunk).filter_by(user_id=category.user_id, category_id=category.id).update(
            {"category_name": category.name}
        )
        vector_store.update_category_metadata(chunk_ids, category.id, category.name)
    db.commit()
    db.refresh(category)
    return category


@router.delete("/categories/{category_id}")
def delete_category(
    category_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    category = db.get(Category, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    fallback = uncategorized_category(db, category.user_id, category.knowledge_base_id)
    if fallback and fallback.id == category.id:
        raise HTTPException(status_code=400, detail="Cannot delete default uncategorized category")
    for document in db.query(Document).filter_by(user_id=category.user_id, category_id=category.id).all():
        assign_document_category(db, document, fallback, classify_status="manual")
    db.query(Category).filter_by(parent_id=category.id, user_id=category.user_id).update({"parent_id": None})
    db.delete(category)
    db.commit()
    return {"ok": True}


@router.get("/documents", response_model=List[AdminDocumentOut])
def list_documents(
    user_id: Optional[int] = None,
    knowledge_base_id: Optional[int] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    query = db.query(Document).filter(Document.deleted_at.is_(None))
    if user_id:
        query = query.filter(Document.user_id == user_id)
    if knowledge_base_id:
        query = query.filter(Document.knowledge_base_id == knowledge_base_id)
    if status:
        query = query.filter(Document.status == status)
    return query.order_by(Document.id.desc()).all()


@router.post("/documents/upload", response_model=AdminDocumentOut)
def upload_document(
    knowledge_base_id: int = Form(...),
    auto_classify: bool = Form(True),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    kb = db.get(KnowledgeBase, knowledge_base_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in SUPPORTED_DOCUMENT_SUFFIXES:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}")

    upload_dir = settings.upload_path / f"user_{kb.user_id}" / f"kb_{kb.id}"
    target = upload_dir / safe_unique_filename(file.filename, "document")
    file_size = save_upload_file(file, target, settings.max_upload_bytes)

    document = Document(
        user_id=kb.user_id,
        knowledge_base_id=kb.id,
        filename=target.name,
        file_type=suffix.lstrip("."),
        file_path=str(target),
        file_size=file_size,
        status="pending",
    )
    db.add(document)
    db.flush()

    enqueue_parse_task(db, document, "admin_upload", "管理员上传文档，等待后台解析", auto_classify=auto_classify)
    db.commit()
    db.refresh(document)
    return document


@router.get("/documents/{document_id}/preview")
def preview_document(
    document_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    chunks = (
        db.query(DocumentChunk)
        .filter_by(document_id=document.id, user_id=document.user_id)
        .order_by(DocumentChunk.chunk_index)
        .limit(PREVIEW_CHUNK_LIMIT)
        .all()
    )
    try:
        path = _resolve_document_path(document)
        blocks, outline, text = _preview_from_file(document, path, chunks)
    except HTTPException:
        text = "\n\n".join(chunk.content for chunk in chunks)
        blocks, outline = _text_blocks_from_plain_text(text)
    return {
        "id": document.id,
        "user_id": document.user_id,
        "filename": document.filename,
        "file_type": document.file_type,
        "knowledge_base_id": document.knowledge_base_id,
        "category_id": document.category_id,
        "category_name": document.category_name,
        "status": document.status,
        "file_size": document.file_size,
        "chunk_count": document.chunk_count,
        "classify_status": document.classify_status,
        "classify_confidence": document.classify_confidence,
        "classify_reason": document.classify_reason,
        "created_at": document.created_at,
        "content": text[:30000],
        "outline": outline[:40],
        "blocks": blocks[:400],
    }


@router.post("/documents/{document_id}/reparse", response_model=DocumentOut)
def reparse_document(
    document_id: int,
    auto_classify: bool = True,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    document.status = "pending"
    enqueue_parse_task(db, document, "admin_reparse", "管理员已加入重建索引队列", auto_classify=auto_classify)
    db.commit()
    db.refresh(document)
    return document


@router.post("/documents/{document_id}/reclassify", response_model=DocumentOut)
def auto_reclassify_document(
    document_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    try:
        reclassify_document(db, document)
    except Exception as exc:
        document.status = "failed"
        document.error_message = str(exc)
    db.commit()
    db.refresh(document)
    return document


@router.delete("/documents/{document_id}")
def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    document.deleted_at = datetime.utcnow()
    document.status = "deleted"
    log_audit(db, _, "admin.document.soft_delete", "document", document.id, {"filename": document.filename})
    db.commit()
    return {"ok": True}


@router.get("/qa-logs", response_model=List[QaLogOut])
def list_qa_logs(
    user_id: Optional[int] = None,
    knowledge_base_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    query = db.query(QaLog)
    if user_id:
        query = query.filter(QaLog.user_id == user_id)
    if knowledge_base_id:
        query = query.filter(QaLog.knowledge_base_id == knowledge_base_id)
    return query.order_by(QaLog.id.desc()).limit(500).all()


@router.delete("/qa-logs/{log_id}")
def delete_qa_log(
    log_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    log = db.get(QaLog, log_id)
    if not log:
        raise HTTPException(status_code=404, detail="QA log not found")
    db.delete(log)
    db.commit()
    return {"ok": True}


@router.get("/evaluations", response_model=List[EvaluationResultOut])
def list_evaluations(
    user_id: Optional[int] = None,
    knowledge_base_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    query = db.query(EvaluationResult)
    if user_id:
        query = query.filter(EvaluationResult.user_id == user_id)
    if knowledge_base_id:
        query = query.filter(EvaluationResult.knowledge_base_id == knowledge_base_id)
    return query.order_by(EvaluationResult.id.desc()).limit(500).all()


@router.delete("/evaluations/{evaluation_id}")
def delete_evaluation(
    evaluation_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    result = db.get(EvaluationResult, evaluation_id)
    if not result:
        raise HTTPException(status_code=404, detail="Evaluation result not found")
    db.delete(result)
    db.commit()
    return {"ok": True}


def _delete_user_owned_data(db: Session, user_id: int) -> None:
    for kb in db.query(KnowledgeBase).filter_by(user_id=user_id).all():
        _delete_knowledge_base_data(db, kb)
        db.delete(kb)
    db.query(QaLog).filter_by(user_id=user_id).delete()
    db.query(EvaluationResult).filter_by(user_id=user_id).delete()
    db.query(ConversationFavorite).filter_by(user_id=user_id).delete()
    db.query(Message).filter_by(user_id=user_id).delete()
    db.query(Conversation).filter_by(user_id=user_id).delete()
    db.flush()


def _delete_knowledge_base_data(db: Session, kb: KnowledgeBase) -> None:
    for document in db.query(Document).filter_by(user_id=kb.user_id, knowledge_base_id=kb.id).all():
        delete_document_data(db, document, remove_file=True)
    db.flush()
    conversation_ids = [
        row[0]
        for row in db.query(Conversation.id)
        .filter_by(user_id=kb.user_id, knowledge_base_id=kb.id)
        .all()
    ]
    if conversation_ids:
        db.query(Message).filter(Message.conversation_id.in_(conversation_ids), Message.user_id == kb.user_id).delete(
            synchronize_session=False
        )
        db.query(ConversationFavorite).filter(
            ConversationFavorite.conversation_id.in_(conversation_ids),
            ConversationFavorite.user_id == kb.user_id,
        ).delete(synchronize_session=False)
    db.query(Conversation).filter_by(user_id=kb.user_id, knowledge_base_id=kb.id).delete()
    db.query(QaLog).filter_by(user_id=kb.user_id, knowledge_base_id=kb.id).delete()
    db.query(EvaluationResult).filter_by(user_id=kb.user_id, knowledge_base_id=kb.id).delete()
    db.query(Category).filter_by(user_id=kb.user_id, knowledge_base_id=kb.id).delete()
    vector_store.delete_knowledge_base(kb.id, kb.user_id)
    db.flush()
