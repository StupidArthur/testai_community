"""
锚点词典：CRUD 与模糊匹配（同义词 + 向量）。
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.ai_service.rag.embeddings import embed_text, embed_texts
from app.data_cleaning.config import (
    ANCHOR_VECTOR_MATCH_THRESHOLD,
    ANCHOR_VECTOR_REVIEW_THRESHOLD,
)
from app.data_cleaning.models import AnchorNode
from app.data_cleaning.runtime import ollama_available
from app.data_cleaning.utils import loads_json

log = logging.getLogger(__name__)

_anchor_embedding_cache: dict[str, list[float]] = {}


def list_anchors(db: Session, *, include_disabled: bool = False) -> list[AnchorNode]:
    q = db.query(AnchorNode)
    if not include_disabled:
        q = q.filter(AnchorNode.enabled.is_(True))
    return q.order_by(AnchorNode.sort_order, AnchorNode.label).all()


def get_anchor(db: Session, anchor_id: str) -> AnchorNode | None:
    return db.query(AnchorNode).filter(AnchorNode.id == anchor_id).first()


def _anchor_search_text(node: AnchorNode) -> str:
    syns = loads_json(node.synonyms_json, [])
    parts = [node.label, node.description or ""] + [str(s) for s in syns]
    return " ".join(p for p in parts if p).strip()


def _synonym_hit(text: str, node: AnchorNode) -> bool:
    hay = text.lower()
    if node.label.lower() in hay:
        return True
    for syn in loads_json(node.synonyms_json, []):
        s = str(syn).strip().lower()
        if len(s) >= 2 and s in hay:
            return True
    return False


async def _ensure_anchor_embeddings(db: Session) -> None:
    nodes = list_anchors(db)
    missing = [n for n in nodes if n.id not in _anchor_embedding_cache]
    if not missing:
        return
    texts = [_anchor_search_text(n) for n in missing]
    try:
        vectors = await embed_texts(texts)
        for node, vec in zip(missing, vectors):
            _anchor_embedding_cache[node.id] = vec
    except Exception as exc:
        log.warning("锚点向量预热失败: %s", exc)


async def match_anchors_for_text(
    db: Session,
    text: str,
    *,
    top_k: int = 3,
) -> list[dict[str, Any]]:
    """
    返回匹配候选：[{anchor_id, label, score, match_type}, ...]
    """
    nodes = list_anchors(db)
    if not nodes:
        return []

    hits: dict[str, dict[str, Any]] = {}

    for node in nodes:
        if _synonym_hit(text, node):
            hits[node.id] = {
                "anchor_id": node.id,
                "label": node.label,
                "score": 0.95,
                "match_type": "synonym",
            }

    try:
        if await ollama_available():
            await _ensure_anchor_embeddings(db)
            if _anchor_embedding_cache:
                qvec = await embed_text(text[:2000])
                for node in nodes:
                    vec = _anchor_embedding_cache.get(node.id)
                    if not vec:
                        continue
                    score = _cosine_similarity(qvec, vec)
                    prev = hits.get(node.id)
                    if prev is None or score > prev["score"]:
                        match_type = "vector" if score >= ANCHOR_VECTOR_MATCH_THRESHOLD else "vector_weak"
                        hits[node.id] = {
                            "anchor_id": node.id,
                            "label": node.label,
                            "score": round(score, 4),
                            "match_type": match_type,
                        }
    except Exception as exc:
        log.warning("锚点向量匹配跳过: %s", exc)

    ranked = sorted(hits.values(), key=lambda x: x["score"], reverse=True)
    return ranked[:top_k]


def pick_anchor_ids(candidates: list[dict[str, Any]]) -> list[str]:
    """自动采纳高置信锚点。"""
    ids: list[str] = []
    for c in candidates:
        score = float(c.get("score") or 0)
        if c.get("match_type") == "synonym" or score >= ANCHOR_VECTOR_MATCH_THRESHOLD:
            aid = str(c.get("anchor_id") or "")
            if aid and aid not in ids:
                ids.append(aid)
    if not ids and candidates:
        top = candidates[0]
        if float(top.get("score") or 0) >= ANCHOR_VECTOR_REVIEW_THRESHOLD:
            ids.append(str(top["anchor_id"]))
    return ids


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)
