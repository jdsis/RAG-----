from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models import KnowledgeBase, User

bearer = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    payload = decode_access_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = db.get(User, int(payload["sub"]))
    if not user or user.status != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive user")
    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin required")
    return current_user


def _permission_set(user: User) -> set[str]:
    raw = (user.permissions or "").strip()
    if not raw:
        return set()
    if raw.startswith("["):
        import json

        try:
            data = json.loads(raw)
            return {str(item).strip() for item in data if str(item).strip()}
        except json.JSONDecodeError:
            return set()
    return {item.strip() for item in raw.split(",") if item.strip()}


def has_permission(user: User, permission: str) -> bool:
    if user.role == "admin":
        return True
    permissions = _permission_set(user)
    if not permissions:
        return True
    return permission in permissions or "*" in permissions


def require_permission(permission: str):
    def dependency(current_user: User = Depends(get_current_user)) -> User:
        if not has_permission(current_user, permission):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Permission required: {permission}")
        return current_user

    return dependency


def ensure_user_knowledge_base(db: Session, user: User, knowledge_base_id: int) -> KnowledgeBase:
    kb = db.query(KnowledgeBase).filter_by(id=knowledge_base_id, user_id=user.id).first()
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")
    return kb
