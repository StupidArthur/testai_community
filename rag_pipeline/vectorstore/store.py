"""
向量库操作（Chroma）。

写入字段与 Chunk schema 对齐；向量化文本使用 chunk_text。
入库不做 LLM 文本生成。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from rag_pipeline.config import CHROMA_COLLECTION, CHROMA_DIR
from rag_pipeline.models.schemas import Chunk
from rag_pipeline.vectorstore.embeddings import EmbedFn, embed_texts, hash_embed_texts

log = logging.getLogger(__name__)

_client = None
_collection = None


def _get_collection(persist_dir: Path | None = None, collection: str | None = None):
    global _client, _collection
    import chromadb
    from chromadb.config import Settings

    directory = str(persist_dir or CHROMA_DIR)
    Path(directory).mkdir(parents=True, exist_ok=True)
    name = collection or CHROMA_COLLECTION
    if _collection is not None and getattr(_collection, "name", None) == name:
        return _collection
    _client = chromadb.PersistentClient(
        path=directory,
        settings=Settings(anonymized_telemetry=False),
    )
    _collection = _client.get_or_create_collection(name=name)
    return _collection


def reset_store_cache() -> None:
    """测试用：清空模块级缓存。"""
    global _client, _collection
    _client = None
    _collection = None


def _meta_from_chunk(c: Chunk) -> dict[str, Any]:
    return {
        "chunk_id": c.chunk_id,
        "doc_id": c.doc_id,
        "doc_title": c.doc_title,
        "raw_text": c.raw_text,
        "chunk_text": c.chunk_text,
        "chapter_path": c.chapter_path,
        "heading_level": c.heading_level,
        "chunk_index": c.chunk_index,
        "prev_chunk_id": c.prev_chunk_id or "",
        "next_chunk_id": c.next_chunk_id or "",
        "is_table": c.is_table,
        "is_list_block": c.is_list_block,
        "key_entities": json.dumps(c.key_entities, ensure_ascii=False),
        "doc_summary": c.doc_summary or "",
        "created_at": c.created_at,
    }


def chunk_from_meta(meta: dict[str, Any]) -> Chunk:
    """从 Chroma metadata 还原 Chunk。"""
    ents = meta.get("key_entities") or "[]"
    if isinstance(ents, str):
        try:
            ents_list = json.loads(ents)
        except json.JSONDecodeError:
            ents_list = []
    else:
        ents_list = list(ents)
    return Chunk(
        chunk_id=str(meta.get("chunk_id") or ""),
        doc_id=str(meta.get("doc_id") or ""),
        doc_title=str(meta.get("doc_title") or ""),
        raw_text=str(meta.get("raw_text") or ""),
        chunk_text=str(meta.get("chunk_text") or ""),
        chapter_path=str(meta.get("chapter_path") or ""),
        heading_level=int(meta.get("heading_level") or 0),
        chunk_index=int(meta.get("chunk_index") or 0),
        prev_chunk_id=str(meta["prev_chunk_id"]) if meta.get("prev_chunk_id") else None,
        next_chunk_id=str(meta["next_chunk_id"]) if meta.get("next_chunk_id") else None,
        is_table=bool(meta.get("is_table")),
        is_list_block=bool(meta.get("is_list_block")),
        key_entities=ents_list,
        doc_summary=str(meta["doc_summary"]) if meta.get("doc_summary") else None,
        created_at=str(meta.get("created_at") or ""),
    )


def upsert_chunks(
    chunks: list[Chunk],
    *,
    embed_fn: EmbedFn | None = None,
    persist_dir: Path | None = None,
) -> int:
    """将 chunks 写入向量库，返回写入条数。"""
    if not chunks:
        return 0
    col = _get_collection(persist_dir)
    fn = embed_fn or embed_texts
    try:
        vectors = fn([c.chunk_text for c in chunks])
    except Exception as exc:  # noqa: BLE001
        log.warning("embed failed (%s), fallback hash_embed", exc)
        vectors = hash_embed_texts([c.chunk_text for c in chunks])

    ids = [c.chunk_id for c in chunks]
    metas = [_meta_from_chunk(c) for c in chunks]
    documents = [c.chunk_text for c in chunks]
    col.upsert(ids=ids, embeddings=vectors, metadatas=metas, documents=documents)
    return len(chunks)


def delete_document(doc_id: str, *, persist_dir: Path | None = None) -> None:
    """按文档删除全部 chunk。"""
    col = _get_collection(persist_dir)
    col.delete(where={"doc_id": doc_id})


def list_doc_summaries(*, persist_dir: Path | None = None) -> list[dict[str, str]]:
    """列出各文档摘要（chunk_index=0）。"""
    col = _get_collection(persist_dir)
    # Chroma where 对 int 可能需注意；用 get 全量再过滤（文档量可控）
    data = col.get(include=["metadatas"])
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for meta in data.get("metadatas") or []:
        if not meta:
            continue
        if int(meta.get("chunk_index") or -1) != 0:
            continue
        doc_id = str(meta.get("doc_id") or "")
        if not doc_id or doc_id in seen:
            continue
        seen.add(doc_id)
        out.append(
            {
                "doc_id": doc_id,
                "doc_title": str(meta.get("doc_title") or ""),
                "doc_summary": str(meta.get("doc_summary") or ""),
            }
        )
    return out


def query_chunks(
    query_vector: list[float],
    *,
    doc_ids: list[str] | None = None,
    top_k: int = 5,
    persist_dir: Path | None = None,
) -> list[Chunk]:
    """向量检索 chunk。"""
    col = _get_collection(persist_dir)
    kwargs: dict[str, Any] = {
        "query_embeddings": [query_vector],
        "n_results": top_k,
        "include": ["metadatas", "documents", "distances"],
    }
    if doc_ids:
        if len(doc_ids) == 1:
            kwargs["where"] = {"doc_id": doc_ids[0]}
        else:
            kwargs["where"] = {"doc_id": {"$in": doc_ids}}
    res = col.query(**kwargs)
    metas = (res.get("metadatas") or [[]])[0]
    return [chunk_from_meta(m) for m in metas if m]
