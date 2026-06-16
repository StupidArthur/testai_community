"""
RAG 检索与问答生成。
"""

from __future__ import annotations

from typing import Any

from app.ai_service.client import chat
from app.platform.config import KB_RAG_TOP_K, MINIMAX_MODEL

from .embeddings import embed_text
from .store import query_kb

RAG_SYSTEM_PROMPT = """你是知识库问答助手。请严格根据「参考资料」回答用户问题。
规则：
1. 仅使用参考资料中的信息，不要编造。
2. 若资料不足以回答，请明确说「根据当前知识库资料无法确定」。
3. 回答使用中文，条理清晰。
4. 可在回答末尾用「参考来源」列出用到的文档名。"""


def _build_context(hits: list[dict[str, Any]]) -> str:
    """将检索结果拼成参考资料文本。"""
    if not hits:
        return "（无相关资料）"
    parts: list[str] = []
    for idx, hit in enumerate(hits, start=1):
        meta = hit.get("metadata") or {}
        filename = meta.get("filename") or meta.get("source") or "未知文档"
        page = meta.get("page", -1)
        page_hint = f" 第{page}页" if isinstance(page, int) and page > 0 else ""
        parts.append(f"【资料{idx}】{filename}{page_hint}\n{hit.get('text', '')}")
    return "\n\n".join(parts)


async def retrieve_context(kb_id: str, question: str, *, top_k: int | None = None) -> list[dict[str, Any]]:
    """检索与问题相关的 chunk。"""
    k = top_k if top_k is not None else KB_RAG_TOP_K
    query_vec = await embed_text(question)
    return query_kb(kb_id, query_vec, top_k=k)


async def answer_with_rag(kb_id: str, question: str, *, top_k: int | None = None) -> dict[str, Any]:
    """
    RAG 问答：检索 + MiniMax 生成。

    返回：{ answer, citations, hits }
    """
    hits = await retrieve_context(kb_id, question, top_k=top_k)
    context = _build_context(hits)
    messages = [
        {"role": "system", "content": RAG_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"参考资料：\n{context}\n\n用户问题：{question}",
        },
    ]
    answer = await chat(messages, model=MINIMAX_MODEL, temperature=0.2, think=False)
    citations = []
    for hit in hits:
        meta = hit.get("metadata") or {}
        citations.append(
            {
                "chunk_id": hit.get("id"),
                "filename": meta.get("filename") or meta.get("source") or "",
                "page": meta.get("page"),
                "snippet": (hit.get("text") or "")[:200],
                "distance": hit.get("distance"),
            }
        )
    return {"answer": answer, "citations": citations, "hits": hits}
