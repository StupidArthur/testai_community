"""
ChromaDB 向量存储封装（延迟加载 chromadb，避免未安装时阻塞 import）。
"""

from __future__ import annotations

import logging
from typing import Any

from app.platform.config import KNOWLEDGE_BASE_CHROMA_DIR

log = logging.getLogger(__name__)

_client: Any = None


def _import_chromadb():
    import chromadb
    from chromadb.config import Settings

    return chromadb, Settings


def _collection_name(kb_id: str) -> str:
    """Chroma collection 名（仅允许字母数字下划线）。"""
    safe = kb_id.replace("-", "_")
    return f"kb_{safe}"


def get_chroma_client():
    """获取 Chroma 持久化客户端单例。"""
    global _client
    if _client is None:
        chromadb, Settings = _import_chromadb()
        KNOWLEDGE_BASE_CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(
            path=str(KNOWLEDGE_BASE_CHROMA_DIR),
            settings=Settings(anonymized_telemetry=False),
        )
    return _client


def get_kb_collection(kb_id: str):
    """获取或创建知识库对应的 collection。"""
    client = get_chroma_client()
    return client.get_or_create_collection(
        name=_collection_name(kb_id),
        metadata={"hnsw:space": "cosine"},
    )


def upsert_chunks(
    kb_id: str,
    *,
    chunk_ids: list[str],
    texts: list[str],
    embeddings: list[list[float]],
    metadatas: list[dict[str, Any]],
) -> None:
    """写入或更新 chunk 向量。"""
    if not chunk_ids:
        return
    collection = get_kb_collection(kb_id)
    collection.upsert(
        ids=chunk_ids,
        documents=texts,
        embeddings=embeddings,
        metadatas=metadatas,
    )


def delete_document_chunks(kb_id: str, doc_id: str) -> None:
    """删除某文档下的全部 chunk（按 metadata.doc_id）。"""
    try:
        collection = get_kb_collection(kb_id)
        collection.delete(where={"doc_id": doc_id})
    except Exception as exc:
        log.warning("删除文档向量失败 kb=%s doc=%s: %s", kb_id, doc_id, exc)


def delete_kb_collection(kb_id: str) -> None:
    """删除整个知识库 collection。"""
    try:
        client = get_chroma_client()
        name = _collection_name(kb_id)
        client.delete_collection(name)
    except Exception as exc:
        log.warning("删除知识库向量 collection 失败 kb=%s: %s", kb_id, exc)


def kb_vector_chunk_count(kb_id: str) -> int:
    """知识库 Chroma 中可检索 chunk 数量（含数据清洗批准的 KU）。"""
    try:
        return int(get_kb_collection(kb_id).count())
    except Exception as exc:
        log.warning("统计知识库向量失败 kb=%s: %s", kb_id, exc)
        return 0


def query_kb(
    kb_id: str,
    query_embedding: list[float],
    *,
    top_k: int = 6,
    active_only: bool = True,
) -> list[dict[str, Any]]:
    """
    向量检索，返回 [{id, text, metadata, distance}, ...]
    active_only=True 时优先仅返回 ku_status=active 或未标 ku 的历史 chunk。
    """
    collection = get_kb_collection(kb_id)
    count = collection.count()
    if count == 0:
        return []
    n = min(top_k * 3 if active_only else top_k, count)
    result = collection.query(
        query_embeddings=[query_embedding],
        n_results=n,
        include=["documents", "metadatas", "distances"],
    )
    ids = (result.get("ids") or [[]])[0]
    docs = (result.get("documents") or [[]])[0]
    metas = (result.get("metadatas") or [[]])[0]
    dists = (result.get("distances") or [[]])[0]
    hits: list[dict[str, Any]] = []
    for i, chunk_id in enumerate(ids):
        meta = metas[i] if i < len(metas) else {}
        if active_only:
            ku_status = (meta or {}).get("ku_status")
            if ku_status is not None and ku_status != "active":
                continue
        hits.append(
            {
                "id": chunk_id,
                "text": docs[i] if i < len(docs) else "",
                "metadata": meta,
                "distance": dists[i] if i < len(dists) else None,
            }
        )
        if len(hits) >= top_k:
            break
    return hits
