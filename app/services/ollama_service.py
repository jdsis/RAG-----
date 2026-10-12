import json
import hashlib
import logging
from typing import Iterator, List, Optional

import requests

from app.core.config import settings
from app.models import User
from app.services.url_guard import validate_model_base_url

logger = logging.getLogger(__name__)


def _hash_embedding(text: str, dimensions: int = 384) -> List[float]:
    vector = [0.0] * dimensions
    tokens = text.lower().replace("\n", " ").split()
    for token in tokens or [text[:80]]:
        digest = hashlib.sha256(token.encode("utf-8", errors="ignore")).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        vector[index] += 1.0
    norm = sum(value * value for value in vector) ** 0.5
    return [value / norm for value in vector] if norm else vector


def _provider(user: Optional[User]) -> str:
    value = (user.model_provider if user else None) or "system"
    return "ollama" if value == "system" else value


def _base_url(user: Optional[User]) -> str:
    if user and user.model_provider and user.model_provider != "system" and user.model_base_url:
        return validate_model_base_url(user.model_base_url)
    return settings.ollama_base_url.rstrip("/")


def _chat_model(user: Optional[User]) -> str:
    return (user.model_chat_model if user else None) or settings.chat_model


def _embedding_model(user: Optional[User]) -> str:
    return (user.model_embedding_model if user else None) or settings.embedding_model


def _headers(user: Optional[User]) -> dict:
    if user and user.model_api_key:
        return {"Authorization": f"Bearer {user.model_api_key}"}
    return {}


def embed_texts(texts: List[str], user: Optional[User] = None) -> List[List[float]]:
    if not texts:
        return []
    try:
        if _provider(user) == "openai_compatible":
            response = requests.post(
                f"{_base_url(user)}/embeddings",
                json={"model": _embedding_model(user), "input": texts},
                headers=_headers(user),
                timeout=settings.ollama_timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
            embeddings = [item.get("embedding", []) for item in data.get("data", [])]
        else:
            response = requests.post(
                f"{_base_url(user)}/api/embed",
                json={"model": _embedding_model(user), "input": texts},
                timeout=settings.ollama_timeout_seconds,
            )
            response.raise_for_status()
            embeddings = response.json().get("embeddings", [])
        return embeddings if len(embeddings) == len(texts) else [_hash_embedding(text) for text in texts]
    except Exception:
        logger.exception("Embedding provider failed; falling back to local hash embeddings")
        return [_hash_embedding(text) for text in texts]


def embed_text(text: str, user: Optional[User] = None) -> List[float]:
    embeddings = embed_texts([text], user=user)
    return embeddings[0] if embeddings else []


def stream_chat(prompt: str, user: Optional[User] = None) -> Iterator[str]:
    if _provider(user) == "openai_compatible":
        yield from _stream_openai_compatible(prompt, user)
        return
    yield from _stream_ollama(prompt, user)


def _stream_ollama(prompt: str, user: Optional[User] = None) -> Iterator[str]:
    try:
        response = requests.post(
            f"{_base_url(user)}/api/chat",
            json={
                "model": _chat_model(user),
                "messages": [{"role": "user", "content": prompt}],
                "stream": True,
            },
            timeout=max(30, settings.ollama_timeout_seconds * 4),
            stream=True,
        )
        response.raise_for_status()
        for line in response.iter_lines():
            if not line:
                continue
            data = json.loads(line.decode("utf-8"))
            token = data.get("message", {}).get("content", "")
            if token:
                yield token
            if data.get("done"):
                break
    except Exception:
        logger.exception("Ollama streaming request failed")
        return


def _stream_openai_compatible(prompt: str, user: Optional[User]) -> Iterator[str]:
    try:
        response = requests.post(
            f"{_base_url(user)}/chat/completions",
            json={
                "model": _chat_model(user),
                "messages": [{"role": "user", "content": prompt}],
                "stream": True,
            },
            headers=_headers(user),
            timeout=max(30, settings.ollama_timeout_seconds * 4),
            stream=True,
        )
        response.raise_for_status()
        for raw_line in response.iter_lines():
            if not raw_line:
                continue
            line = raw_line.decode("utf-8")
            if line.startswith("data:"):
                line = line.replace("data:", "", 1).strip()
            if line == "[DONE]":
                break
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            token = data.get("choices", [{}])[0].get("delta", {}).get("content", "")
            if token:
                yield token
    except Exception:
        logger.exception("OpenAI-compatible streaming request failed")
        return
