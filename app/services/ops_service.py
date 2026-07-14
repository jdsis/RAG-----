from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog, SystemAlert, User


def log_audit(
    db: Session,
    user: User | None,
    action: str,
    target_type: str | None = None,
    target_id: str | int | None = None,
    detail: dict[str, Any] | str | None = None,
) -> None:
    if isinstance(detail, dict):
        detail = json.dumps(detail, ensure_ascii=False)
    db.add(
        AuditLog(
            user_id=user.id if user else None,
            username=user.username if user else None,
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            detail=detail,
        )
    )


def open_alert(db: Session, level: str, title: str, message: str | None = None) -> None:
    db.add(SystemAlert(level=level, title=title, message=message, status="open"))
