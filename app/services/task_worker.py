from __future__ import annotations

import logging
import threading
import time

from app.core.database import SessionLocal
from app.models import Document, ParseTask
from app.services.document_service import process_document

logger = logging.getLogger(__name__)

_worker_started = False
_worker_lock = threading.Lock()


def start_parse_worker() -> None:
    global _worker_started
    with _worker_lock:
        if _worker_started:
            return
        thread = threading.Thread(target=_worker_loop, name="parse-task-worker", daemon=True)
        thread.start()
        _worker_started = True


def enqueue_parse_task(db, document: Document, task_type: str, message: str, auto_classify: bool = True) -> ParseTask:
    task = ParseTask(
        user_id=document.user_id,
        document_id=document.id,
        filename=document.filename,
        task_type=task_type,
        status="pending",
        progress=0,
        message=message,
    )
    # Store the auto-classify preference in the message payload without adding another column.
    task.message = f"{message} | auto_classify={str(auto_classify).lower()}"
    db.add(task)
    return task


def _worker_loop() -> None:
    while True:
        try:
            _process_next_task()
        except Exception:
            logger.exception("Parse worker loop failed")
        time.sleep(1.5)


def _process_next_task() -> None:
    db = SessionLocal()
    try:
        task = (
            db.query(ParseTask)
            .filter(ParseTask.status == "pending", ParseTask.document_id.isnot(None))
            .order_by(ParseTask.id)
            .first()
        )
        if not task:
            return
        original_message = task.message or ""
        task.status = "running"
        task.progress = 10
        task.message = "后台解析任务已开始"
        db.commit()

        document = db.get(Document, task.document_id)
        if not document:
            task.status = "failed"
            task.progress = 100
            task.message = "文档不存在"
            db.commit()
            return

        task.progress = 35
        task.message = "正在解析文档、识别 OCR 并切分文本"
        db.commit()
        auto_classify = "auto_classify=false" not in original_message
        process_document(db, document, auto_classify=auto_classify)
        task.status = "completed"
        task.progress = 100
        task.message = "解析完成"
        db.commit()
    except Exception as exc:
        db.rollback()
        try:
            if "task" in locals() and task:
                task.status = "failed"
                task.progress = 100
                task.message = str(exc)
                if task.document_id:
                    document = db.get(Document, task.document_id)
                    if document:
                        document.status = "failed"
                        document.error_message = str(exc)
                db.commit()
        except Exception:
            db.rollback()
            logger.exception("Failed to mark parse task as failed")
    finally:
        db.close()
