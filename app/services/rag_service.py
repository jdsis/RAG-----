from __future__ import annotations

import json
import math
import re
import time
from collections import Counter
from typing import Iterable, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Conversation, DocumentChunk, Message, QaLog, User
from app.services.ollama_service import embed_text, stream_chat
from app.services.vector_store import vector_store

NO_ANSWER = "根据当前知识库资料，我没有找到明确答案。"


def _tokens(text: str) -> List[str]:
    return re.findall(r"[\w\u4e00-\u9fff]+", text.lower())


def _text_score(question: str, content: str) -> float:
    q = Counter(_tokens(question))
    c = Counter(_tokens(content))
    if not q or not c:
        return 0
    dot = sum(q[t] * c.get(t, 0) for t in q)
    return dot / (math.sqrt(sum(v * v for v in q.values())) * math.sqrt(sum(v * v for v in c.values())))


def _cosine_score(left: List[float], right: List[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if not left_norm or not right_norm:
        return 0
    return dot / (left_norm * right_norm)


def _load_embedding(chunk: DocumentChunk) -> List[float]:
    if not chunk.embedding_json:
        return []
    try:
        data = json.loads(chunk.embedding_json)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def retrieve_chunks(db: Session, user: User, knowledge_base_id: int, question: str, category_id: Optional[int] = None):
    query = db.query(DocumentChunk).filter(
        DocumentChunk.user_id == user.id,
        DocumentChunk.knowledge_base_id == knowledge_base_id,
    )
    if category_id:
        query = query.filter(DocumentChunk.category_id == category_id)
    chunks = query.all()

    question_embedding = embed_text(question, user=user)
    vector_ids = vector_store.query(
        question_embedding,
        user_id=user.id,
        knowledge_base_id=knowledge_base_id,
        category_id=category_id,
        top_k=settings.top_k,
    )
    if vector_ids:
        chunk_by_id = {chunk.vector_id: chunk for chunk in chunks}
        ordered_chunks = [chunk_by_id[vector_id] for vector_id in vector_ids if vector_id in chunk_by_id]
        if ordered_chunks:
            return ordered_chunks

    vector_ranked: List[Tuple[float, DocumentChunk]] = []
    if question_embedding:
        for chunk in chunks:
            score = _cosine_score(question_embedding, _load_embedding(chunk))
            if score > 0:
                vector_ranked.append((score, chunk))

    if vector_ranked:
        ranked = sorted(vector_ranked, key=lambda item: item[0], reverse=True)
    else:
        ranked = sorted(
            ((_text_score(question, chunk.content), chunk) for chunk in chunks),
            key=lambda item: item[0],
            reverse=True,
        )
    return [chunk for score, chunk in ranked[: settings.top_k] if score > 0]


def build_prompt(question: str, chunks: List[DocumentChunk]) -> str:
    context = "\n\n".join(
        f"[{i}] 来源: {chunk.source_name}, 页码: {chunk.page_number or '-'}, 片段: {chunk.content[:700]}"
        for i, chunk in enumerate(chunks[: settings.top_k], 1)
    )
    return f"""你是一个技术知识库问答助手。
请严格根据【参考资料】回答用户问题。
要求：
1. 只能使用参考资料中的内容回答。
2. 如果参考资料中没有答案，请回答：“{NO_ANSWER}”
3. 不要整段复制原文，不要输出 JSON，不要输出 content_preview。
4. 不要使用 Markdown 加粗符号，例如不要输出 **标题**。
5. 优先用自己的话概括，回答控制在 150 到 350 字。
6. 涉及技术步骤时，请给出简洁操作流程。
7. 回答末尾用“参考来源：文档名 / 片段编号”列出来源。

【用户问题】
{question}

【参考资料】
{context}

【回答】"""


def _fallback_answer(chunks: List[DocumentChunk]) -> str:
    if not chunks:
        return NO_ANSWER
    lines = ["根据当前知识库资料，可归纳为："]
    for index, chunk in enumerate(chunks, 1):
        preview = chunk.content[:180].replace("\n", " ")
        lines.append(f"{index}. {preview}")
    lines.append("引用来源：")
    for chunk in chunks:
        page = f"第 {chunk.page_number} 页" if chunk.page_number else "未标注页码"
        lines.append(f"- {chunk.source_name}，{page}，片段 {chunk.chunk_index}")
    return "\n".join(lines)


def _clean_answer(answer: str) -> str:
    return (
        answer.replace("**", "")
        .replace("__", "")
        .replace("###", "")
        .replace("##", "")
        .strip()
    )


def answer_stream(db: Session, user: User, request) -> Iterable[str]:
    start = time.time()
    chunks = retrieve_chunks(db, user, request.knowledge_base_id, request.question, request.category_id)
    conversation = db.get(Conversation, request.conversation_id) if request.conversation_id else None
    if not conversation:
        conversation = Conversation(
            user_id=user.id,
            knowledge_base_id=request.knowledge_base_id,
            category_id=request.category_id,
            title=request.question[:80],
        )
        db.add(conversation)
        db.flush()
    db.add(Message(user_id=user.id, conversation_id=conversation.id, role="user", content=request.question))
    db.commit()

    answer_parts: List[str] = []
    if chunks:
        token_buffer = ""
        for token in stream_chat(build_prompt(request.question, chunks), user=user):
            token_buffer += token
            clean_token = token.replace("**", "").replace("__", "")
            answer_parts.append(clean_token)
            yield clean_token
    if not answer_parts:
        fallback = _fallback_answer(chunks)
        for char in fallback:
            answer_parts.append(char)
            yield char

    answer = _clean_answer("".join(answer_parts))
    source_payload = [
        {
            "document_id": chunk.document_id,
            "document_name": chunk.source_name,
            "page_number": chunk.page_number,
            "chunk_index": chunk.chunk_index,
            "content_preview": chunk.content[:160],
        }
        for chunk in chunks
    ]
    db.add(Message(user_id=user.id, conversation_id=conversation.id, role="assistant", content=answer))
    db.add(
        QaLog(
            user_id=user.id,
            knowledge_base_id=request.knowledge_base_id,
            category_id=request.category_id,
            conversation_id=conversation.id,
            question=request.question,
            answer=answer,
            retrieved_chunks=json.dumps(source_payload, ensure_ascii=False),
            response_time_ms=int((time.time() - start) * 1000),
            is_answered=answer.strip() != NO_ANSWER,
        )
    )
    db.commit()
    yield "\n"
    yield f"event: sources\ndata: {json.dumps(source_payload, ensure_ascii=False)}\n\n"
