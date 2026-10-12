from __future__ import annotations

from typing import Dict, List, Optional

from app.core.config import settings

COLLECTION_NAME = "rag_kb_chunks"


class ChromaVectorStore:
    def __init__(self) -> None:
        self._collection = None

    @property
    def collection(self):
        if self._collection is None:
            import chromadb

            settings.chroma_path.mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=str(settings.chroma_path))
            self._collection = client.get_or_create_collection(name=COLLECTION_NAME)
        return self._collection

    def available(self) -> bool:
        try:
            _ = self.collection
            return True
        except Exception:
            return False

    def upsert_chunks(
        self,
        ids: List[str],
        documents: List[str],
        embeddings: List[List[float]],
        metadatas: List[Dict],
    ) -> None:
        if not ids or not embeddings or len(ids) != len(embeddings):
            return
        try:
            self.collection.upsert(
                ids=ids,
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas,
            )
        except Exception:
            return

    def query(
        self,
        question_embedding: List[float],
        user_id: int,
        knowledge_base_id: int,
        category_id: Optional[int] = None,
        top_k: Optional[int] = None,
    ) -> List[str]:
        if not question_embedding:
            return []
        where_items = [
            {"user_id": user_id},
            {"knowledge_base_id": knowledge_base_id},
        ]
        if category_id:
            where_items.append({"category_id": category_id})
        where = {"$and": where_items} if len(where_items) > 1 else where_items[0]
        try:
            result = self.collection.query(
                query_embeddings=[question_embedding],
                n_results=top_k or settings.top_k,
                where=where,
            )
            return result.get("ids", [[]])[0]
        except Exception:
            return []

    def delete_document(self, document_id: int, user_id: int) -> None:
        try:
            self.collection.delete(where={"$and": [{"document_id": document_id}, {"user_id": user_id}]})
        except Exception:
            return

    def delete_knowledge_base(self, knowledge_base_id: int, user_id: int) -> None:
        try:
            self.collection.delete(where={"$and": [{"knowledge_base_id": knowledge_base_id}, {"user_id": user_id}]})
        except Exception:
            return

    def update_category_metadata(self, ids: List[str], category_id: Optional[int], category_name: Optional[str]) -> None:
        if not ids:
            return
        try:
            rows = self.collection.get(ids=ids, include=["metadatas"])
            metadatas = []
            for metadata in rows.get("metadatas", []):
                metadata = dict(metadata or {})
                metadata["category_id"] = category_id or 0
                metadata["category_name"] = category_name or ""
                metadatas.append(metadata)
            if metadatas:
                self.collection.update(ids=ids, metadatas=metadatas)
        except Exception:
            return


vector_store = ChromaVectorStore()
