from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class UserCreate(BaseModel):
    username: str
    email: str
    email_code: str
    password: str
    confirm_password: str
    captcha_token: str
    captcha_answer: str
    accepted_terms: bool = False


class EmailVerificationRequest(BaseModel):
    email: str
    captcha_token: str
    captcha_answer: str


class LoginRequest(BaseModel):
    username: str
    password: str
    portal: Optional[str] = None
    captcha_token: str
    captcha_answer: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: Optional[str] = None
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    signature: Optional[str] = None
    role: str
    status: str
    created_at: datetime
    reset_invite_expires_at: Optional[datetime] = None
    document_quota: Optional[int] = None
    storage_quota_mb: Optional[int] = None
    query_quota: Optional[int] = None
    permissions: Optional[str] = None


class UserProfileUpdate(BaseModel):
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    signature: Optional[str] = None


class PasswordUpdate(BaseModel):
    current_password: str
    new_password: str


class PasswordInviteReset(BaseModel):
    username: str
    invite_code: str
    new_password: str


class AdminPasswordInviteOut(BaseModel):
    user_id: int
    username: str
    invite_code: str
    expires_at: datetime


class UserModelSettingsOut(BaseModel):
    provider: str = "system"
    base_url: Optional[str] = None
    chat_model: Optional[str] = None
    embedding_model: Optional[str] = None
    api_key_configured: bool = False
    effective_provider: str
    effective_base_url: str
    effective_chat_model: str
    effective_embedding_model: str


class UserModelSettingsUpdate(BaseModel):
    provider: str = "system"
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    chat_model: Optional[str] = None
    embedding_model: Optional[str] = None


class AdminUserCreate(BaseModel):
    username: str
    password: str
    role: str = "user"
    status: str = "active"


class AdminUserUpdate(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None
    role: Optional[str] = None
    status: Optional[str] = None
    document_quota: Optional[int] = None
    storage_quota_mb: Optional[int] = None
    query_quota: Optional[int] = None
    permissions: Optional[str] = None


class AdminSettingsOut(BaseModel):
    app_name: str
    database_url: str
    upload_dir: str
    jwt_expire_minutes: int
    jwt_secret_configured: bool
    ollama_base_url: str
    chat_model: str
    embedding_model: str
    ollama_timeout_seconds: int
    chroma_dir: str
    chunk_size: int
    chunk_overlap: int
    top_k: int
    restart_required_keys: List[str] = []


class AdminSettingsUpdate(BaseModel):
    app_name: Optional[str] = None
    database_url: Optional[str] = None
    upload_dir: Optional[str] = None
    jwt_secret_key: Optional[str] = None
    jwt_expire_minutes: Optional[int] = None
    ollama_base_url: Optional[str] = None
    chat_model: Optional[str] = None
    embedding_model: Optional[str] = None
    ollama_timeout_seconds: Optional[int] = None
    chroma_dir: Optional[str] = None
    chunk_size: Optional[int] = None
    chunk_overlap: Optional[int] = None
    top_k: Optional[int] = None


class KnowledgeBaseCreate(BaseModel):
    name: str
    description: Optional[str] = None


class KnowledgeBaseUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class KnowledgeBaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: Optional[str] = None
    vector_store_type: str
    created_at: datetime


class AdminKnowledgeBaseOut(KnowledgeBaseOut):
    user_id: int


class CategoryCreate(BaseModel):
    knowledge_base_id: int
    name: str
    description: Optional[str] = None
    parent_id: Optional[int] = None


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    parent_id: Optional[int] = None


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    knowledge_base_id: int
    name: str
    description: Optional[str] = None
    parent_id: Optional[int] = None


class AdminCategoryOut(CategoryOut):
    user_id: int


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    knowledge_base_id: int
    category_id: Optional[int] = None
    category_name: Optional[str] = None
    filename: str
    file_type: str
    status: str
    classify_status: str
    classify_confidence: float
    classify_reason: Optional[str] = None
    chunk_count: int
    file_size: int = 0
    error_message: Optional[str] = None
    version: int = 1
    deleted_at: Optional[datetime] = None
    created_at: datetime


class AdminDocumentOut(DocumentOut):
    user_id: int
    file_path: str


class ChangeDocumentCategory(BaseModel):
    category_id: Optional[int] = None


class WebDocumentCreate(BaseModel):
    knowledge_base_id: int
    url: str
    auto_classify: bool = True


class ChatRequest(BaseModel):
    knowledge_base_id: int
    question: str
    category_id: Optional[int] = None
    conversation_id: Optional[int] = None


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    knowledge_base_id: int
    category_id: Optional[int] = None
    title: str
    created_at: datetime


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    content: str
    created_at: datetime


class EvaluationCase(BaseModel):
    question: str
    expected_keywords: List[str] = []


class EvaluationRunRequest(BaseModel):
    knowledge_base_id: int
    cases: List[EvaluationCase]


class QaLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    knowledge_base_id: int
    category_id: Optional[int] = None
    conversation_id: Optional[int] = None
    question: str
    answer: str
    retrieved_chunks: str
    response_time_ms: int
    is_answered: bool
    created_at: datetime


class EvaluationResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    knowledge_base_id: int
    test_question: str
    expected_keywords: str
    actual_answer: str
    hit: bool
    response_time_ms: int
    no_answer: bool
    created_at: datetime


class DocumentVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    version: int
    filename: str
    file_size: int
    change_note: Optional[str] = None
    created_at: datetime


class ParseTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: Optional[int] = None
    filename: str
    task_type: str
    status: str
    progress: int
    message: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class AnswerFeedbackCreate(BaseModel):
    conversation_id: Optional[int] = None
    message_id: Optional[int] = None
    qa_log_id: Optional[int] = None
    rating: str
    comment: Optional[str] = None


class KnowledgeBaseShareCreate(BaseModel):
    username: str
    permission: str = "read"


class KnowledgeBaseShareOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    knowledge_base_id: int
    owner_id: int
    target_user_id: int
    permission: str
    created_at: datetime


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: Optional[int] = None
    username: Optional[str] = None
    action: str
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    detail: Optional[str] = None
    created_at: datetime


class ConfigChangeHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: Optional[int] = None
    key: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    created_at: datetime


class SystemAlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    level: str
    title: str
    message: Optional[str] = None
    status: str
    created_at: datetime
