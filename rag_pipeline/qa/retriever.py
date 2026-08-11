"""
检索：先用 doc_summary 粗筛命中文档，再在文档内用 chunk_text 向量检索。
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from rag_pipeline.config import DOC_SUMMARY_PREFILTER_LIMIT, RETRIEVE_TOP_K
from rag_pipeline.models.schemas import Chunk
from rag_pipeline.vectorstore.embeddings import EmbedFn, embed_texts, hash_embed_texts
from rag_pipeline.vectorstore.store import list_doc_summaries, query_chunks

log = logging.getLogger(__name__)


def _keyword_score(question: str, summary: str) -> float:
    """无向量时的粗筛：字符 bigram / 词重叠。"""
    q = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9]{2,}", question)
    if not q:
        return 0.0
    s = summary or ""
    hit = sum(1 for t in q if t in s)
    return hit / len(q)


def prefilter_docs(
    question: str,
    *,
    persist_dir: Path | None = None,
    limit: int = DOC_SUMMARY_PREFILTER_LIMIT,
) -> list[str]:
    """基于 doc_summary 粗筛文档 ID。"""
    docs = list_doc_summaries(persist_dir=persist_dir)
    if not docs:
        return []
    scored = sorted(
        docs,
        key=lambda d: _keyword_score(question, d.get("doc_summary") or d.get("doc_title") or ""),
        reverse=True,
    )
    # 若全 0 分，保留全部（再交给向量检索）
    if scored and _keyword_score(question, scored[0].get("doc_summary") or "") <= 0:
        return [d["doc_id"] for d in docs[:limit]]
    return [d["doc_id"] for d in scored[:limit] if _keyword_score(question, d.get("doc_summary") or "") > 0] or [
        d["doc_id"] for d in scored[: min(3, len(scored))]
    ]


def retrieve_chunks(
    question: str,
    *,
    top_k: int = RETRIEVE_TOP_K,
    persist_dir: Path | None = None,
    embed_fn: EmbedFn | None = None,
) -> list[Chunk]:
    """根据用户问题检索相关 chunk。"""
    doc_ids = prefilter_docs(question, persist_dir=persist_dir)
    fn = embed_fn or embed_texts
    try:
        qvec = fn([question])[0]
    except Exception as exc:  # noqa: BLE001
        log.warning("query embed failed (%s), use hash", exc)
        qvec = hash_embed_texts([question])[0]
    return query_chunks(qvec, doc_ids=doc_ids or None, top_k=top_k, persist_dir=persist_dir)
