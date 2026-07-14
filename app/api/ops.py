from __future__ import annotations

import json
import shutil
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import requests
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy import func, or_, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import Base, engine, get_db
from app.deps import get_current_user, require_admin, require_permission
from app.models import (
    AnswerFeedback,
    AuditLog,
    Category,
    ConfigChangeHistory,
    Conversation,
    Document,
    DocumentChunk,
    DocumentVersion,
    KnowledgeBase,
    KnowledgeBaseShare,
    Message,
    ParseTask,
    QaLog,
    SystemAlert,
    User,
)
from app.schemas import (
    AnswerFeedbackCreate,
    AuditLogOut,
    ConfigChangeHistoryOut,
    DocumentVersionOut,
    KnowledgeBaseShareCreate,
    KnowledgeBaseShareOut,
    ParseTaskOut,
    SystemAlertOut,
)
from app.services.ops_service import log_audit, open_alert
from app.services.task_worker import enqueue_parse_task
from app.services.vector_store import vector_store

router = APIRouter(tags=["operations"])


def _owned_or_shared_kb_ids(db: Session, user: User) -> list[int]:
    owned = [row[0] for row in db.query(KnowledgeBase.id).filter_by(user_id=user.id, deleted_at=None).all()]
    shared = [
        row[0]
        for row in db.query(KnowledgeBaseShare.knowledge_base_id)
        .filter_by(target_user_id=user.id)
        .all()
    ]
    return sorted(set(owned + shared))


@router.get("/tasks", response_model=List[ParseTaskOut])
def list_my_tasks(current_user: User = Depends(require_permission("task:read")), db: Session = Depends(get_db)):
    return db.query(ParseTask).filter_by(user_id=current_user.id).order_by(ParseTask.id.desc()).limit(100).all()


@router.get("/documents/{document_id}/versions", response_model=List[DocumentVersionOut])
def list_document_versions(
    document_id: int,
    current_user: User = Depends(require_permission("document:read")),
    db: Session = Depends(get_db),
):
    document = db.query(Document).filter_by(id=document_id, user_id=current_user.id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return db.query(DocumentVersion).filter_by(document_id=document_id, user_id=current_user.id).order_by(DocumentVersion.version.desc()).all()


@router.post("/documents/{document_id}/versions", response_model=DocumentVersionOut)
def upload_document_version(
    document_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(require_permission("document:version")),
    db: Session = Depends(get_db),
):
    document = db.query(Document).filter_by(id=document_id, user_id=current_user.id, deleted_at=None).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    target_dir = settings.upload_path / f"user_{current_user.id}" / f"kb_{document.knowledge_base_id}" / "versions"
    target_dir.mkdir(parents=True, exist_ok=True)
    next_version = (document.version or 1) + 1
    target = target_dir / f"doc_{document.id}_v{next_version}_{Path(file.filename or document.filename).name}"
    with target.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    version = DocumentVersion(
        user_id=current_user.id,
        document_id=document.id,
        version=next_version,
        filename=target.name,
        file_path=str(target),
        file_size=target.stat().st_size,
        change_note="用户上传新版本",
    )
    document.version = next_version
    document.filename = target.name
    document.file_path = str(target)
    document.file_size = target.stat().st_size
    document.status = "pending"
    db.add(version)
    enqueue_parse_task(db, document, "version", "新版本已上传，等待后台重建索引", auto_classify=True)
    log_audit(db, current_user, "document.version.upload", "document", document.id, {"version": next_version})
    db.commit()
    db.refresh(version)
    return version


@router.get("/search")
def cross_knowledge_search(
    q: str,
    knowledge_base_ids: Optional[str] = None,
    current_user: User = Depends(require_permission("search:cross")),
    db: Session = Depends(get_db),
):
    query_text = q.strip()
    if not query_text:
        return []
    available_ids = _owned_or_shared_kb_ids(db, current_user)
    if knowledge_base_ids:
        requested = {int(item) for item in knowledge_base_ids.split(",") if item.strip().isdigit()}
        available_ids = [item for item in available_ids if item in requested]
    if not available_ids:
        return []
    rows = (
        db.query(DocumentChunk, Document, KnowledgeBase)
        .join(Document, Document.id == DocumentChunk.document_id)
        .join(KnowledgeBase, KnowledgeBase.id == DocumentChunk.knowledge_base_id)
        .filter(
            DocumentChunk.knowledge_base_id.in_(available_ids),
            Document.deleted_at.is_(None),
            DocumentChunk.content.like(f"%{query_text}%"),
        )
        .limit(50)
        .all()
    )
    return [
        {
            "knowledge_base_id": kb.id,
            "knowledge_base_name": kb.name,
            "document_id": document.id,
            "document_name": document.filename,
            "chunk_index": chunk.chunk_index,
            "page_number": chunk.page_number,
            "preview": chunk.content[:260],
        }
        for chunk, document, kb in rows
    ]


@router.post("/answer-feedback")
def create_answer_feedback(
    payload: AnswerFeedbackCreate,
    current_user: User = Depends(require_permission("feedback:create")),
    db: Session = Depends(get_db),
):
    if payload.rating not in {"up", "down", "neutral"}:
        raise HTTPException(status_code=400, detail="rating must be up, down or neutral")
    feedback = AnswerFeedback(user_id=current_user.id, **payload.model_dump())
    db.add(feedback)
    log_audit(db, current_user, "answer.feedback", "conversation", payload.conversation_id, payload.model_dump())
    db.commit()
    return {"ok": True, "id": feedback.id}


@router.get("/conversations/search")
def search_conversations(q: str, current_user: User = Depends(require_permission("chat:read")), db: Session = Depends(get_db)):
    query_text = q.strip()
    if not query_text:
        return []
    rows = (
        db.query(Conversation)
        .join(Message, Message.conversation_id == Conversation.id)
        .filter(
            Conversation.user_id == current_user.id,
            or_(Conversation.title.like(f"%{query_text}%"), Message.content.like(f"%{query_text}%")),
        )
        .order_by(Conversation.id.desc())
        .distinct()
        .limit(50)
        .all()
    )
    return rows


@router.get("/conversations/{conversation_id}/export")
def export_conversation(conversation_id: int, current_user: User = Depends(require_permission("chat:export")), db: Session = Depends(get_db)):
    conversation = db.query(Conversation).filter_by(id=conversation_id, user_id=current_user.id).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    messages = db.query(Message).filter_by(user_id=current_user.id, conversation_id=conversation_id).order_by(Message.id).all()
    body = [f"# {conversation.title}", ""]
    for message in messages:
        role = "用户" if message.role == "user" else "助手"
        body.extend([f"## {role} {message.created_at}", message.content, ""])
    return PlainTextResponse("\n".join(body), media_type="text/markdown; charset=utf-8")


@router.get("/knowledge-bases/{knowledge_base_id}/shares", response_model=List[KnowledgeBaseShareOut])
def list_kb_shares(
    knowledge_base_id: int,
    current_user: User = Depends(require_permission("knowledge_base:share")),
    db: Session = Depends(get_db),
):
    kb = db.query(KnowledgeBase).filter_by(id=knowledge_base_id, user_id=current_user.id, deleted_at=None).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return db.query(KnowledgeBaseShare).filter_by(knowledge_base_id=knowledge_base_id, owner_id=current_user.id).all()


@router.post("/knowledge-bases/{knowledge_base_id}/shares", response_model=KnowledgeBaseShareOut)
def create_kb_share(
    knowledge_base_id: int,
    payload: KnowledgeBaseShareCreate,
    current_user: User = Depends(require_permission("knowledge_base:share")),
    db: Session = Depends(get_db),
):
    kb = db.query(KnowledgeBase).filter_by(id=knowledge_base_id, user_id=current_user.id, deleted_at=None).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    target = db.query(User).filter_by(username=payload.username).first()
    if not target:
        raise HTTPException(status_code=404, detail="Target user not found")
    if target.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot share to yourself")
    permission = payload.permission if payload.permission in {"read", "write"} else "read"
    share = db.query(KnowledgeBaseShare).filter_by(knowledge_base_id=kb.id, target_user_id=target.id).first()
    if share:
        share.permission = permission
    else:
        share = KnowledgeBaseShare(knowledge_base_id=kb.id, owner_id=current_user.id, target_user_id=target.id, permission=permission)
        db.add(share)
    log_audit(db, current_user, "knowledge_base.share", "knowledge_base", kb.id, {"target": target.username, "permission": permission})
    db.commit()
    db.refresh(share)
    return share


@router.delete("/knowledge-bases/{knowledge_base_id}/shares/{share_id}")
def delete_kb_share(
    knowledge_base_id: int,
    share_id: int,
    current_user: User = Depends(require_permission("knowledge_base:share")),
    db: Session = Depends(get_db),
):
    share = db.query(KnowledgeBaseShare).filter_by(id=share_id, knowledge_base_id=knowledge_base_id, owner_id=current_user.id).first()
    if not share:
        raise HTTPException(status_code=404, detail="Share not found")
    db.delete(share)
    log_audit(db, current_user, "knowledge_base.share.delete", "knowledge_base", knowledge_base_id)
    db.commit()
    return {"ok": True}


@router.get("/admin/audit-logs", response_model=List[AuditLogOut])
def list_audit_logs(limit: int = 200, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    return db.query(AuditLog).order_by(AuditLog.id.desc()).limit(min(max(limit, 1), 500)).all()


@router.put("/admin/users/{user_id}/quota")
def update_user_quota(
    user_id: int,
    payload: dict,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    for key in ["document_quota", "storage_quota_mb", "query_quota", "permissions"]:
        if key in payload:
            setattr(user, key, payload[key])
    log_audit(db, current_admin, "user.quota.update", "user", user_id, payload)
    db.commit()
    return {"ok": True}


@router.get("/admin/tasks", response_model=List[ParseTaskOut])
def list_all_tasks(status: Optional[str] = None, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    query = db.query(ParseTask)
    if status:
        query = query.filter(ParseTask.status == status)
    return query.order_by(ParseTask.id.desc()).limit(300).all()


@router.get("/admin/trash")
def list_trash(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    documents = db.query(Document).filter(Document.deleted_at.is_not(None)).order_by(Document.deleted_at.desc()).limit(200).all()
    kbs = db.query(KnowledgeBase).filter(KnowledgeBase.deleted_at.is_not(None)).order_by(KnowledgeBase.deleted_at.desc()).limit(200).all()
    return {
        "documents": documents,
        "knowledge_bases": kbs,
    }


@router.post("/admin/trash/{item_type}/{item_id}/restore")
def restore_trash_item(
    item_type: str,
    item_id: int,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if item_type == "document":
        item = db.get(Document, item_id)
    elif item_type == "knowledge_base":
        item = db.get(KnowledgeBase, item_id)
    else:
        raise HTTPException(status_code=400, detail="Unsupported trash item type")
    if not item:
        raise HTTPException(status_code=404, detail="Trash item not found")
    item.deleted_at = None
    log_audit(db, current_admin, "trash.restore", item_type, item_id)
    db.commit()
    return {"ok": True}


@router.get("/admin/model-test")
def test_model_connectivity(_: User = Depends(require_admin)):
    started = time.time()
    try:
        response = requests.get(f"{settings.ollama_base_url.rstrip('/')}/api/tags", timeout=settings.ollama_timeout_seconds)
        return {
            "ok": response.ok,
            "status_code": response.status_code,
            "latency_ms": int((time.time() - started) * 1000),
            "base_url": settings.ollama_base_url,
        }
    except Exception as exc:
        return {"ok": False, "latency_ms": int((time.time() - started) * 1000), "base_url": settings.ollama_base_url, "error": str(exc)}


@router.get("/admin/vector-health")
def vector_health(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    db_chunks = db.query(func.count(DocumentChunk.id)).scalar() or 0
    available = vector_store.available()
    vector_count = None
    try:
        vector_count = vector_store.collection.count()
    except Exception:
        vector_count = None
    return {
        "available": available,
        "database_chunks": db_chunks,
        "vector_chunks": vector_count,
        "chroma_dir": str(settings.chroma_path),
        "consistent": vector_count is None or vector_count == db_chunks,
    }


def _json_value(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _restore_value(column, value):
    if value is None:
        return None
    if "DateTime" in column.type.__class__.__name__ and isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return value
    return value


def _write_database_snapshot(snapshot_path: Path, db: Session) -> dict:
    tables = {}
    counts = {}
    for table in Base.metadata.sorted_tables:
        rows = db.execute(table.select()).mappings().all()
        tables[table.name] = [
            {column.name: _json_value(row[column.name]) for column in table.columns}
            for row in rows
        ]
        counts[table.name] = len(rows)
    payload = {
        "created_at": datetime.utcnow().isoformat(),
        "database_url": settings.database_url,
        "tables": tables,
    }
    snapshot_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return counts


def _create_backup_archive(db: Session, prefix: str = "backup") -> Path:
    backup_dir = Path("data/backups")
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    snapshot_path = backup_dir / f"{prefix}-{timestamp}.db.json"
    archive_path = backup_dir / f"{prefix}-{timestamp}.zip"
    counts = _write_database_snapshot(snapshot_path, db)
    metadata_path = backup_dir / f"{prefix}-{timestamp}.metadata.json"
    metadata_path.write_text(
        json.dumps({"created_at": datetime.utcnow().isoformat(), "counts": counts}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(snapshot_path, "db.json")
        archive.write(metadata_path, "metadata.json")
        env_path = Path(".env")
        if env_path.exists():
            archive.write(env_path, ".env.snapshot")
        upload_root = settings.upload_path
        if upload_root.exists():
            for path in upload_root.rglob("*"):
                if path.is_file():
                    archive.write(path, f"uploads/{path.relative_to(upload_root).as_posix()}")
    snapshot_path.unlink(missing_ok=True)
    metadata_path.unlink(missing_ok=True)
    return archive_path


@router.post("/admin/backup")
def create_backup(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    archive_path = _create_backup_archive(db)
    log_audit(db, current_admin, "backup.create", "backup", archive_path.name)
    db.commit()
    return {"ok": True, "filename": archive_path.name, "path": str(archive_path)}


@router.get("/admin/backups")
def list_backups(_: User = Depends(require_admin)):
    backup_dir = Path("data/backups")
    if not backup_dir.exists():
        return []
    return [
        {"filename": item.name, "size": item.stat().st_size, "created_at": datetime.fromtimestamp(item.stat().st_mtime)}
        for item in sorted(backup_dir.glob("*.zip"), key=lambda path: path.stat().st_mtime, reverse=True)
    ]


@router.get("/admin/backups/{filename}")
def download_backup(filename: str, _: User = Depends(require_admin)):
    path = Path("data/backups") / filename
    if not path.exists() or path.suffix != ".zip":
        raise HTTPException(status_code=404, detail="Backup not found")
    return FileResponse(path)


def _safe_extract_backup(file: UploadFile) -> Path:
    restore_dir = Path("data/restores") / datetime.utcnow().strftime("%Y%m%d%H%M%S")
    restore_dir.mkdir(parents=True, exist_ok=True)
    archive_path = restore_dir / Path(file.filename or "backup.zip").name
    with archive_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            target = (restore_dir / member.filename).resolve()
            if not str(target).startswith(str(restore_dir.resolve())):
                raise HTTPException(status_code=400, detail="Invalid backup archive path")
        archive.extractall(restore_dir)
    return restore_dir


def _restore_uploads(restore_dir: Path) -> None:
    upload_snapshot = restore_dir / "uploads"
    if not upload_snapshot.exists():
        return
    current_upload = settings.upload_path
    if current_upload.exists():
        backup_upload = current_upload.with_name(f"{current_upload.name}.before_restore_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}")
        shutil.move(str(current_upload), str(backup_upload))
    shutil.copytree(upload_snapshot, current_upload)


def _restore_database_from_snapshot(snapshot_path: Path) -> None:
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    tables = payload.get("tables") or {}
    with engine.begin() as connection:
        if engine.dialect.name == "mysql":
            connection.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(table.delete())
        for table in Base.metadata.sorted_tables:
            rows = tables.get(table.name, [])
            if not rows:
                continue
            converted = []
            for row in rows:
                converted.append({column.name: _restore_value(column, row.get(column.name)) for column in table.columns})
            connection.execute(table.insert(), converted)
        if engine.dialect.name == "mysql":
            connection.execute(text("SET FOREIGN_KEY_CHECKS=1"))


@router.post("/admin/restore")
def restore_backup(
    file: UploadFile = File(...),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    before_restore = _create_backup_archive(db, prefix="before-restore")
    restore_dir = _safe_extract_backup(file)
    snapshot_path = restore_dir / "db.json"
    if not snapshot_path.exists():
        raise HTTPException(status_code=400, detail="Backup archive does not contain db.json")
    _restore_database_from_snapshot(snapshot_path)
    _restore_uploads(restore_dir)
    open_alert(db, "warning", "备份恢复已执行", f"已恢复 {file.filename}，恢复前备份为 {before_restore.name}。")
    log_audit(db, current_admin, "backup.restore", "backup", file.filename, {"before_restore": before_restore.name})
    db.commit()
    return {"ok": True, "message": f"备份已恢复。恢复前备份：{before_restore.name}"}


@router.get("/admin/config-history", response_model=List[ConfigChangeHistoryOut])
def list_config_history(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return db.query(ConfigChangeHistory).order_by(ConfigChangeHistory.id.desc()).limit(300).all()


@router.get("/admin/alerts", response_model=List[SystemAlertOut])
def list_alerts(status: Optional[str] = None, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    query = db.query(SystemAlert)
    if status:
        query = query.filter(SystemAlert.status == status)
    return query.order_by(SystemAlert.id.desc()).limit(200).all()


@router.put("/admin/alerts/{alert_id}")
def update_alert(alert_id: int, payload: dict, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    alert = db.get(SystemAlert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.status = payload.get("status", alert.status)
    log_audit(db, current_admin, "alert.update", "alert", alert_id, payload)
    db.commit()
    return {"ok": True}
