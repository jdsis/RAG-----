from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def load_env_file(path: str = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env_file()


def _csv_env(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


def _bool_env(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    app_name: str = os.getenv("APP_NAME", "RAG Knowledge Base")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./data/rag_kb.db")
    upload_dir: str = os.getenv("UPLOAD_DIR", "./data/uploads")
    jwt_secret_key: str = os.getenv("JWT_SECRET_KEY") or secrets.token_urlsafe(32)
    jwt_secret_configured: bool = bool(os.getenv("JWT_SECRET_KEY"))
    jwt_expire_minutes: int = int(os.getenv("JWT_EXPIRE_MINUTES", str(60 * 24 * 7)))
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    chat_model: str = os.getenv("CHAT_MODEL", "qwen3:8b")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "qwen3-embedding:0.6b")
    ollama_timeout_seconds: int = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "8"))
    chroma_dir: str = os.getenv("CHROMA_DIR", "./data/chroma")
    chunk_size: int = int(os.getenv("CHUNK_SIZE", "600"))
    chunk_overlap: int = int(os.getenv("CHUNK_OVERLAP", "100"))
    top_k: int = int(os.getenv("TOP_K", "5"))
    cors_origins: list[str] = None
    max_upload_bytes: int = int(os.getenv("MAX_UPLOAD_BYTES", str(50 * 1024 * 1024)))
    max_avatar_bytes: int = int(os.getenv("MAX_AVATAR_BYTES", str(2 * 1024 * 1024)))
    max_web_page_bytes: int = int(os.getenv("MAX_WEB_PAGE_BYTES", str(2 * 1024 * 1024)))
    allowed_model_hosts: list[str] = None
    allow_private_model_urls: bool = _bool_env("ALLOW_PRIVATE_MODEL_URLS")
    allow_private_web_urls: bool = _bool_env("ALLOW_PRIVATE_WEB_URLS")
    smtp_host: str = os.getenv("SMTP_HOST", "")
    smtp_port: int = int(os.getenv("SMTP_PORT", "465"))
    smtp_username: str = os.getenv("SMTP_USERNAME", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    smtp_from_email: str = os.getenv("SMTP_FROM_EMAIL", os.getenv("SMTP_USERNAME", ""))
    smtp_from_name: str = os.getenv("SMTP_FROM_NAME", "技术知识库问答系统")
    smtp_use_ssl: bool = _bool_env("SMTP_USE_SSL", "true")
    smtp_use_tls: bool = _bool_env("SMTP_USE_TLS", "false")

    def __post_init__(self) -> None:
        if self.cors_origins is None:
            self.cors_origins = _csv_env(
                "CORS_ORIGINS",
                "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5183,http://127.0.0.1:5183",
            )
        if self.allowed_model_hosts is None:
            self.allowed_model_hosts = _csv_env("ALLOWED_MODEL_HOSTS")

    @property
    def upload_path(self) -> Path:
        return Path(self.upload_dir)

    @property
    def chroma_path(self) -> Path:
        return Path(self.chroma_dir)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
