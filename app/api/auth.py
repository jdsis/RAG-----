from __future__ import annotations

import time
import re
import secrets
import hashlib
import smtplib
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, create_signed_payload, decode_signed_payload, hash_password, verify_password
from app.models import User
from app.deps import get_current_user
from app.schemas import (
    EmailVerificationRequest,
    LoginRequest,
    PasswordUpdate,
    PasswordInviteReset,
    TokenResponse,
    UserCreate,
    UserModelSettingsOut,
    UserModelSettingsUpdate,
    UserOut,
    UserProfileUpdate,
)
from app.services.email_service import EmailNotConfiguredError, send_email
from app.services.upload_utils import safe_unique_filename, save_upload_file
from app.services.url_guard import validate_model_base_url

router = APIRouter(prefix="/auth", tags=["auth"])

AVATAR_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
RATE_LIMIT_WINDOW_SECONDS = 60
RATE_LIMIT_MAX_ATTEMPTS = 8
LOGIN_LOCK_THRESHOLD = 5
LOGIN_LOCK_MINUTES = 15
EMAIL_CODE_EXPIRE_SECONDS = 10 * 60
EMAIL_CODE_RESEND_SECONDS = 60
EMAIL_CODE_MAX_VERIFY_ATTEMPTS = 5
_rate_limit: dict[str, list[float]] = {}
_used_captcha_tokens: set[str] = set()
_email_codes: dict[str, dict[str, object]] = {}


def _check_rate_limit(key: str) -> None:
    now = time.time()
    recent = [item for item in _rate_limit.get(key, []) if now - item < RATE_LIMIT_WINDOW_SECONDS]
    if len(recent) >= RATE_LIMIT_MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Too many attempts, please try again later")
    recent.append(now)
    _rate_limit[key] = recent


def _client_key(request: Request, scope: str, identity: str = "") -> str:
    host = request.client.host if request.client else "unknown"
    return f"{scope}:{host}:{identity.strip().lower()}"


def _validate_username(username: str) -> str:
    value = username.strip()
    if not re.fullmatch(r"[A-Za-z0-9_]{3,32}", value):
        raise HTTPException(status_code=400, detail="用户名需为 3-32 位字母、数字或下划线")
    return value


def _validate_email(email: str) -> str:
    value = email.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
        raise HTTPException(status_code=400, detail="请输入有效邮箱地址")
    return value


def _validate_password_policy(password: str, confirm_password: str | None = None) -> None:
    if confirm_password is not None and password != confirm_password:
        raise HTTPException(status_code=400, detail="两次输入的密码不一致")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="密码至少 8 位")
    checks = [
        re.search(r"[a-z]", password),
        re.search(r"[A-Z]", password),
        re.search(r"\d", password),
        re.search(r"[^A-Za-z0-9]", password),
    ]
    if sum(bool(item) for item in checks) < 3:
        raise HTTPException(status_code=400, detail="密码需至少包含大写字母、小写字母、数字、特殊符号中的三类")
    weak_words = {"password", "12345678", "qwerty", "admin123", "letmein"}
    if password.lower() in weak_words:
        raise HTTPException(status_code=400, detail="密码过于常见，请更换更安全的密码")


def _hash_email_code(email: str, code: str) -> str:
    data = f"{email}:{code}:{settings.jwt_secret_key}".encode()
    return hashlib.sha256(data).hexdigest()


def _cleanup_email_codes() -> None:
    now = time.time()
    expired = [
        email
        for email, item in _email_codes.items()
        if float(item.get("expires_at", 0)) < now
    ]
    for email in expired:
        _email_codes.pop(email, None)


def _verify_email_code(email: str, code: str) -> None:
    _cleanup_email_codes()
    item = _email_codes.get(email)
    if not item:
        raise HTTPException(status_code=400, detail="邮箱验证码无效或已过期")
    attempts = int(item.get("attempts", 0))
    if attempts >= EMAIL_CODE_MAX_VERIFY_ATTEMPTS:
        _email_codes.pop(email, None)
        raise HTTPException(status_code=400, detail="邮箱验证码已失效，请重新获取")
    expected = str(item.get("code_hash", ""))
    actual = _hash_email_code(email, str(code or "").strip())
    if not secrets.compare_digest(expected, actual):
        item["attempts"] = attempts + 1
        raise HTTPException(status_code=400, detail="邮箱验证码错误")
    _email_codes.pop(email, None)


def _verify_captcha(token: str, answer: str) -> None:
    token = (token or "").strip()
    if not token or token in _used_captcha_tokens:
        raise HTTPException(status_code=400, detail="验证码已失效，请刷新后重试")
    payload = decode_signed_payload(token)
    if not payload or payload.get("purpose") != "captcha":
        raise HTTPException(status_code=400, detail="验证码无效或已过期")
    expected = str(payload.get("answer", "")).strip()
    if not secrets.compare_digest(expected, str(answer or "").strip()):
        raise HTTPException(status_code=400, detail="验证码错误")
    _used_captcha_tokens.add(token)
    if len(_used_captcha_tokens) > 5000:
        _used_captcha_tokens.clear()


@router.get("/captcha")
def captcha():
    left = secrets.randbelow(8) + 2
    right = secrets.randbelow(8) + 1
    operator = "+" if secrets.randbelow(2) == 0 else "-"
    answer = left + right if operator == "+" else left - right
    question = f"{left} {operator} {right} = ?"
    token = create_signed_payload(
        {"purpose": "captcha", "answer": str(answer), "nonce": secrets.token_urlsafe(8)},
        expires_seconds=180,
    )
    return {"question": question, "token": token, "expires_in": 180}


@router.post("/email-code")
def send_register_email_code(payload: EmailVerificationRequest, request: Request, db: Session = Depends(get_db)):
    _verify_captcha(payload.captcha_token, payload.captcha_answer)
    email = _validate_email(payload.email)
    _check_rate_limit(_client_key(request, "email-code", email))
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="Email already exists")

    now = time.time()
    existing = _email_codes.get(email)
    if existing and now - float(existing.get("sent_at", 0)) < EMAIL_CODE_RESEND_SECONDS:
        raise HTTPException(status_code=429, detail="验证码发送过于频繁，请稍后再试")

    code = f"{secrets.randbelow(900000) + 100000}"
    _email_codes[email] = {
        "code_hash": _hash_email_code(email, code),
        "expires_at": now + EMAIL_CODE_EXPIRE_SECONDS,
        "sent_at": now,
        "attempts": 0,
    }
    subject = "技术知识库问答系统注册验证码"
    body = (
        f"您的注册验证码是：{code}\n\n"
        f"验证码将在 {EMAIL_CODE_EXPIRE_SECONDS // 60} 分钟后失效。"
        "如果不是您本人操作，请忽略这封邮件。"
    )
    try:
        send_email(email, subject, body)
    except EmailNotConfiguredError as exc:
        _email_codes.pop(email, None)
        raise HTTPException(status_code=503, detail="邮件服务未配置，请联系管理员") from exc
    except (smtplib.SMTPException, OSError) as exc:
        _email_codes.pop(email, None)
        raise HTTPException(status_code=502, detail="邮件发送失败，请稍后再试") from exc

    return {"ok": True, "expires_in": EMAIL_CODE_EXPIRE_SECONDS}


@router.post("/register", response_model=TokenResponse)
def register(payload: UserCreate, request: Request, db: Session = Depends(get_db)):
    _check_rate_limit(_client_key(request, "register", payload.username))
    _verify_captcha(payload.captcha_token, payload.captcha_answer)
    if not payload.accepted_terms:
        raise HTTPException(status_code=400, detail="请先阅读并同意用户协议与隐私条款")
    username = _validate_username(payload.username)
    email = _validate_email(payload.email)
    _validate_password_policy(payload.password, payload.confirm_password)
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=400, detail="Username already exists")
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="Email already exists")
    _verify_email_code(email, payload.email_code)
    user = User(
        username=username,
        email=email,
        display_name=username,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return TokenResponse(access_token=create_access_token(str(user.id)))


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    identity = payload.username.strip().lower()
    _check_rate_limit(_client_key(request, "login", identity))
    _verify_captcha(payload.captcha_token, payload.captcha_answer)
    user = db.query(User).filter(or_(User.username == payload.username, User.email == identity)).first()
    if user and user.locked_until and user.locked_until > datetime.utcnow():
        raise HTTPException(status_code=423, detail=f"账号已临时锁定，请在 {user.locked_until.isoformat(timespec='minutes')} 后重试")
    if not user or not verify_password(payload.password, user.password_hash):
        if user:
            user.failed_login_count = (user.failed_login_count or 0) + 1
            if user.failed_login_count >= LOGIN_LOCK_THRESHOLD:
                user.locked_until = datetime.utcnow() + timedelta(minutes=LOGIN_LOCK_MINUTES)
                user.failed_login_count = 0
            db.commit()
        raise HTTPException(status_code=401, detail="Invalid username or password")
    if user.status != "active":
        raise HTTPException(status_code=403, detail="User account is disabled")
    portal = (payload.portal or "").strip().lower()
    if portal not in {"user", "admin"}:
        raise HTTPException(status_code=400, detail="Login portal is required")
    if portal == "user" and user.role == "admin":
        raise HTTPException(status_code=403, detail="Admin account can only log in to the admin portal")
    if portal == "admin" and user.role != "admin":
        raise HTTPException(status_code=403, detail="User account can only log in to the user portal")
    user.failed_login_count = 0
    user.locked_until = None
    db.commit()
    return TokenResponse(access_token=create_access_token(str(user.id)))


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.put("/me", response_model=UserOut)
def update_me(
    payload: UserProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    changed_fields = payload.model_fields_set
    display_name = (payload.display_name or "").strip()
    avatar_url = (payload.avatar_url or "").strip()
    signature = (payload.signature or "").strip()

    if "display_name" in changed_fields and not display_name:
        raise HTTPException(status_code=400, detail="Display name cannot be empty")

    if "display_name" in changed_fields:
        current_user.display_name = display_name[:128]
    if "avatar_url" in changed_fields:
        current_user.avatar_url = avatar_url[:500] or None
    if "signature" in changed_fields:
        current_user.signature = signature[:500] or None

    db.commit()
    db.refresh(current_user)
    return current_user


@router.post("/me/avatar")
def upload_my_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in AVATAR_SUFFIXES:
        raise HTTPException(status_code=400, detail="Only jpg, png, webp or gif images are supported")
    if file.content_type and not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image files are supported")

    avatar_dir = settings.upload_path / "avatars" / f"user_{current_user.id}"
    target = avatar_dir / safe_unique_filename(file.filename, "avatar")
    save_upload_file(file, target, settings.max_avatar_bytes)

    relative = target.relative_to(settings.upload_path).as_posix()
    return {"avatar_url": f"/uploads/{relative}"}


@router.put("/me/password", response_model=UserOut)
def update_my_password(
    payload: PasswordUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _validate_password_policy(payload.new_password)
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    current_user.password_hash = hash_password(payload.new_password)
    db.commit()
    db.refresh(current_user)
    return current_user


@router.post("/password/reset-with-invite")
def reset_password_with_invite(payload: PasswordInviteReset, db: Session = Depends(get_db)):
    username = payload.username.strip()
    invite_code = payload.invite_code.strip()
    _check_rate_limit(f"password-reset:{username.lower()}")
    _validate_password_policy(payload.new_password)
    if not username or not invite_code:
        raise HTTPException(status_code=400, detail="Username and invite code are required")

    user = db.query(User).filter(User.username == username).first()
    if (
        not user
        or not user.reset_invite_code
        or user.reset_invite_code != invite_code
        or not user.reset_invite_expires_at
        or user.reset_invite_expires_at < datetime.utcnow()
    ):
        raise HTTPException(status_code=400, detail="Invalid or expired invite code")

    user.password_hash = hash_password(payload.new_password)
    user.reset_invite_code = None
    user.reset_invite_expires_at = None
    user.status = "active"
    db.commit()
    return {"ok": True}


@router.get("/me/model-settings", response_model=UserModelSettingsOut)
def get_my_model_settings(current_user: User = Depends(get_current_user)):
    return _model_settings_out(current_user)


@router.put("/me/model-settings", response_model=UserModelSettingsOut)
def update_my_model_settings(
    payload: UserModelSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    provider = (payload.provider or "system").strip()
    base_url = (payload.base_url or "").strip()
    chat_model = (payload.chat_model or "").strip()
    embedding_model = (payload.embedding_model or "").strip()
    api_key = (payload.api_key or "").strip()
    if provider not in {"system", "ollama", "openai_compatible"}:
        raise HTTPException(status_code=400, detail="Invalid model provider")
    if provider == "openai_compatible":
        if not base_url:
            raise HTTPException(status_code=400, detail="API Base URL is required")
        base_url = validate_model_base_url(base_url)
        if not chat_model:
            raise HTTPException(status_code=400, detail="Chat model is required")
        if not current_user.model_api_key and not api_key:
            raise HTTPException(status_code=400, detail="API Key is required")
    if provider == "ollama" and not chat_model:
        raise HTTPException(status_code=400, detail="Chat model is required")
    if provider == "ollama" and base_url:
        base_url = validate_model_base_url(base_url)

    current_user.model_provider = provider
    current_user.model_base_url = base_url[:500] or None
    current_user.model_chat_model = chat_model[:128] or None
    current_user.model_embedding_model = embedding_model[:128] or None
    if payload.api_key is not None and api_key:
        current_user.model_api_key = api_key[:1000]

    db.commit()
    db.refresh(current_user)
    return _model_settings_out(current_user)


def _model_settings_out(user: User) -> UserModelSettingsOut:
    provider = user.model_provider or "system"
    effective_provider = provider if provider != "system" else "ollama"
    return UserModelSettingsOut(
        provider=provider,
        base_url=user.model_base_url,
        chat_model=user.model_chat_model,
        embedding_model=user.model_embedding_model,
        api_key_configured=bool(user.model_api_key),
        effective_provider=effective_provider,
        effective_base_url=user.model_base_url or settings.ollama_base_url,
        effective_chat_model=user.model_chat_model or settings.chat_model,
        effective_embedding_model=user.model_embedding_model or settings.embedding_model,
    )
