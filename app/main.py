from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text

from app.api import admin, auth, category, chat, document, evaluation, knowledge_base, ops
from app.core.config import settings
from app.core.database import Base, engine
from app.services.task_worker import start_parse_worker


def ensure_schema() -> None:
    inspector = inspect(engine)
    preparer = engine.dialect.identifier_preparer
    table_names = inspector.get_table_names()

    def add_column_if_missing(table_name: str, column_name: str, definition: str) -> None:
        if table_name not in table_names:
            return
        columns = {column["name"] for column in inspector.get_columns(table_name)}
        if column_name in columns:
            return
        quoted_table = preparer.quote(table_name)
        with engine.begin() as connection:
            connection.execute(text(f"ALTER TABLE {quoted_table} ADD COLUMN {column_name} {definition}"))

    if "document_chunk" in table_names:
        columns = {column["name"] for column in inspector.get_columns("document_chunk")}
        if "embedding_json" not in columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE document_chunk ADD COLUMN embedding_json TEXT"))

    if "user" in table_names:
        user_columns = {column["name"] for column in inspector.get_columns("user")}
        user_table = preparer.quote("user")
        with engine.begin() as connection:
            if "display_name" not in user_columns:
                connection.execute(text(f"ALTER TABLE {user_table} ADD COLUMN display_name VARCHAR(128)"))
            if "email" not in user_columns:
                connection.execute(text(f"ALTER TABLE {user_table} ADD COLUMN email VARCHAR(255)"))
            if "avatar_url" not in user_columns:
                connection.execute(text(f"ALTER TABLE {user_table} ADD COLUMN avatar_url VARCHAR(500)"))
            if "signature" not in user_columns:
                connection.execute(text(f"ALTER TABLE {user_table} ADD COLUMN signature TEXT"))
            if "model_provider" not in user_columns:
                connection.execute(text(f"ALTER TABLE {user_table} ADD COLUMN model_provider VARCHAR(32)"))
            if "model_base_url" not in user_columns:
                connection.execute(text(f"ALTER TABLE {user_table} ADD COLUMN model_base_url VARCHAR(500)"))
            if "model_api_key" not in user_columns:
                connection.execute(text(f"ALTER TABLE {user_table} ADD COLUMN model_api_key VARCHAR(1000)"))
            if "model_chat_model" not in user_columns:
                connection.execute(text(f"ALTER TABLE {user_table} ADD COLUMN model_chat_model VARCHAR(128)"))
            if "model_embedding_model" not in user_columns:
                connection.execute(text(f"ALTER TABLE {user_table} ADD COLUMN model_embedding_model VARCHAR(128)"))
            if "reset_invite_code" not in user_columns:
                connection.execute(text(f"ALTER TABLE {user_table} ADD COLUMN reset_invite_code VARCHAR(16)"))
            if "reset_invite_expires_at" not in user_columns:
                connection.execute(text(f"ALTER TABLE {user_table} ADD COLUMN reset_invite_expires_at DATETIME"))
            if "document_quota" not in user_columns:
                connection.execute(text(f"ALTER TABLE {user_table} ADD COLUMN document_quota INTEGER"))
            if "storage_quota_mb" not in user_columns:
                connection.execute(text(f"ALTER TABLE {user_table} ADD COLUMN storage_quota_mb INTEGER"))
            if "query_quota" not in user_columns:
                connection.execute(text(f"ALTER TABLE {user_table} ADD COLUMN query_quota INTEGER"))
            if "permissions" not in user_columns:
                connection.execute(text(f"ALTER TABLE {user_table} ADD COLUMN permissions TEXT"))
            if "failed_login_count" not in user_columns:
                connection.execute(text(f"ALTER TABLE {user_table} ADD COLUMN failed_login_count INTEGER DEFAULT 0"))
            if "locked_until" not in user_columns:
                connection.execute(text(f"ALTER TABLE {user_table} ADD COLUMN locked_until DATETIME"))

    add_column_if_missing("knowledge_base", "deleted_at", "DATETIME")
    add_column_if_missing("category", "deleted_at", "DATETIME")
    add_column_if_missing("document", "version", "INTEGER DEFAULT 1")
    add_column_if_missing("document", "deleted_at", "DATETIME")


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    def on_startup():
        Base.metadata.create_all(bind=engine)
        ensure_schema()
        settings.upload_path.mkdir(parents=True, exist_ok=True)
        settings.chroma_path.mkdir(parents=True, exist_ok=True)
        start_parse_worker()

    @app.get("/")
    def root():
        return {"message": "RAG Knowledge Base API", "docs": "/docs"}

    settings.upload_path.mkdir(parents=True, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=str(settings.upload_path)), name="uploads")

    app.include_router(auth.router, prefix="/api")
    app.include_router(knowledge_base.router, prefix="/api")
    app.include_router(category.router, prefix="/api")
    app.include_router(document.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")
    app.include_router(ops.router, prefix="/api")
    app.include_router(admin.router, prefix="/api")
    app.include_router(evaluation.router, prefix="/api")
    return app


app = create_app()
