"""
与库内已有知识精判对齐（召回 + LLM）。
"""

from __future__ import annotations

import logging
from typing import Any

from app.ai_service.client import chat
from app.ai_service.rag.embeddings import embed_text
from app.ai_service.rag.store import get_kb_collection, query_kb
from app.data_cleaning.config import ALIGN_MIN_CONFIDENCE, ALIGN_RECALL_MAX_DISTANCE
from app.data_cleaning.runtime import ollama_available
from app.data_cleaning.utils import extract_json_object

log = logging.getLogger(__name__)

_ALIGN_SYSTEM = """你是知识一致性审查助手。比较「新精华」与「库内已有资料」，判断关系。
只输出 JSON 对象：
{
  "relation": "same_fact|update|scoped_difference|contradiction|unrelated",
  "confidence": 0.0-1.0,
  "topic": "主题简述",
  "new_claim": "新资料核心结论",
  "old_claim": "旧资料核心结论",
  "recommended_action": "add|supersede|coexist|skip",
  "reason": "简短理由"
}
规则：
- 同版本同环境下矛盾 → contradiction
- 明确版本升级变更 → update，建议 supersede
- 仅环境/版本不同且可并存 → scoped_difference，建议 coexist
- 内容重复 → same_fact，建议 skip
- 不相关 → unrelated
"""


async def align_essence_with_kb(
    kb_id: str,
    essence: str,
    *,
    anchor_id: str = "",
    scope: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """召回库内 chunk 并精判，返回 alignment 列表。"""
    if not essence.strip():
        return []
    if not await ollama_available():
        return []
    try:
        if get_kb_collection(kb_id).count() == 0:
            return []
    except Exception as exc:
        log.warning("库内 chunk 计数失败: %s", exc)
        return []
    try:
        qvec = await embed_text(essence[:2000])
        hits = query_kb(kb_id, qvec, top_k=5)
    except Exception as exc:
        log.warning("库内召回失败: %s", exc)
        return []

    alignments: list[dict[str, Any]] = []
    scope = scope or {}
    for hit in hits:
        dist = hit.get("distance")
        if dist is not None and float(dist) > ALIGN_RECALL_MAX_DISTANCE:
            continue
        meta = hit.get("metadata") or {}
        old_text = (hit.get("text") or "")[:1500]
        judged = await _judge_pair(essence, old_text, scope, meta)
        judged["chunk_id"] = hit.get("id")
        judged["old_snippet"] = old_text[:300]
        judged["old_ku_id"] = meta.get("ku_id") or ""
        judged["old_filename"] = meta.get("filename") or ""
        judged["distance"] = dist
        if judged.get("relation") == "unrelated":
            continue
        if float(judged.get("confidence") or 0) < ALIGN_MIN_CONFIDENCE:
            judged["relation"] = "possible_related"
        alignments.append(judged)
        if anchor_id and len(alignments) >= 2:
            break
    return alignments


async def _judge_pair(
    new_text: str,
    old_text: str,
    scope: dict[str, Any],
    meta: dict[str, Any],
) -> dict[str, Any]:
    user = (
        f"新精华 scope: {scope}\n"
        f"库内 metadata: {meta}\n\n"
        f"【新精华】\n{new_text[:2000]}\n\n"
        f"【库内资料】\n{old_text[:2000]}"
    )
    try:
        out = await chat(
            [
                {"role": "system", "content": _ALIGN_SYSTEM},
                {"role": "user", "content": user},
            ],
            temperature=0.1,
            max_tokens=1024,
            think=False,
        )
        data = extract_json_object(out)
        if not data:
            return {"relation": "unrelated", "confidence": 0.0, "recommended_action": "add"}
        return {
            "relation": str(data.get("relation") or "unrelated"),
            "confidence": float(data.get("confidence") or 0.5),
            "topic": str(data.get("topic") or ""),
            "new_claim": str(data.get("new_claim") or ""),
            "old_claim": str(data.get("old_claim") or ""),
            "recommended_action": str(data.get("recommended_action") or "add"),
            "reason": str(data.get("reason") or ""),
        }
    except Exception as exc:
        log.warning("精判失败: %s", exc)
        return {"relation": "unrelated", "confidence": 0.0, "recommended_action": "add"}


def default_review_action(alignments: list[dict[str, Any]]) -> str:
    """根据精判结果给出默认审核动作。"""
    if not alignments:
        return "add"
    top = alignments[0]
    rel = top.get("relation")
    action = top.get("recommended_action")
    if rel == "contradiction":
        return "pending"
    if action in ("supersede", "coexist", "skip", "add"):
        return str(action)
    if rel == "update":
        return "supersede"
    if rel == "scoped_difference":
        return "coexist"
    if rel == "same_fact":
        return "skip"
    return "add"
