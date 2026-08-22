"""
RAG 检索与问答生成。

流程概览：
1. 结合对话历史扩展检索 query（解决「这个数据来源」等追问指代不清）
2. 向量检索 Chroma → 按问题类型重排 chunk（避免 HTTP 接口与前端页面指标混排）
3. 拼装参考资料 + 多轮历史 → 调用 MiniMax 生成回答
"""

from __future__ import annotations

from typing import Any

from app.ai_service.client import chat
from app.platform.config import KB_RAG_TOP_K, MINIMAX_MODEL

from .embeddings import embed_text
from .store import query_kb

# 送入 LLM 的最近对话轮数（user+assistant 各算一条）
RAG_HISTORY_MESSAGE_LIMIT = 4

# 追问指代词：出现这些词且有历史时，将上一轮问答拼入检索 query
FOLLOWUP_HINTS = ("这个", "上面", "刚才", "前述", "之前", "前面", "上述", "它", "其")

# 来源追问：用户问的是「指标/数据出自哪份文档」，而非系统架构
SOURCE_ATTRIBUTION_HINTS = ("来源", "哪里", "哪里来", "哪来的", "出自", "哪份", "哪个文档", "哪一节", "出自哪")

# 检索重排：问题侧关键词 → 优先匹配的 chunk 侧关键词
SCOPE_KEYWORD_GROUPS: dict[str, tuple[str, ...]] = {
    "http_api": (
        "http",
        "api",
        "接口",
        "请求",
        "并发",
        "响应时间",
        "后端",
        "登录接口",
        "post",
        "get",
    ),
    "frontend_page": (
        "前端",
        "页面",
        "加载",
        "资源",
        "字体",
        "首次加载",
        "静态",
        "下载",
        "页面加载",
    ),
}

# 重排加分 / 减分（在向量距离基础上的微调，数值无需精确，仅用于同批 chunk 内排序）
SCOPE_MATCH_BONUS = 0.15
SCOPE_MISMATCH_PENALTY = 0.12

RAG_SYSTEM_PROMPT = """你是知识库问答助手。请严格根据「参考资料」与「对话历史」回答用户问题。

规则：
1. 仅使用参考资料中的信息，不要编造。
2. 若资料不足以回答，请明确说「根据当前知识库资料无法确定」。
3. 回答使用中文，条理清晰。
4. 只回答用户明确询问的内容；不要主动扩展无关章节。
   - 用户问 HTTP/API/接口/后端性能时，不要混入前端页面加载、字体下载等指标。
   - 用户问前端页面/资源加载时，不要混入 HTTP 接口压测数据。
5. 若用户问「数据/指标来源于哪里、哪份文档、哪一节」，应回答文档名与章节/页码；
   不要猜测数据库、缓存、接口等系统架构（除非资料中明确写了）。
6. 若存在对话历史，结合上下文理解指代词（如「这个」「上面提到的」）。
7. 可在回答末尾用「参考来源」列出用到的文档名。
8. 如果参考资料中包含多个并列项（如多个层级、多个模块），必须列出所有提到的项，不得遗漏。
   如果资料中只提到部分项，回答时如实说明「资料中提到了以下X个」，不要说「仅详细说明了这一层」这种暗示资料不完整的话。"""


def _build_context(hits: list[dict[str, Any]]) -> str:
    """将检索结果拼成参考资料文本，供 LLM 阅读。"""
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


def _normalize_history(history: list[dict[str, str]] | None) -> list[dict[str, str]]:
    """清洗并截断对话历史，仅保留 user/assistant 文本。"""
    if not history:
        return []
    cleaned: list[dict[str, str]] = []
    for item in history[-RAG_HISTORY_MESSAGE_LIMIT:]:
        role = (item.get("role") or "").strip()
        content = (item.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            cleaned.append({"role": role, "content": content})
    return cleaned


def _is_followup_question(question: str) -> bool:
    """是否为依赖上下文的追问。"""
    q = question.strip()
    return any(h in q for h in FOLLOWUP_HINTS)


def _is_source_attribution_question(question: str) -> bool:
    """是否在追问指标/内容的文档出处。"""
    q = question.strip()
    return any(h in q for h in SOURCE_ATTRIBUTION_HINTS)


def _detect_scope(question: str) -> str | None:
    """
    判断问题更偏向哪类测试/内容。
    返回 SCOPE_KEYWORD_GROUPS 的 key，或 None（不做重排）。
    """
    q = question.lower()
    api_score = sum(1 for kw in SCOPE_KEYWORD_GROUPS["http_api"] if kw.lower() in q or kw in question)
    fe_score = sum(1 for kw in SCOPE_KEYWORD_GROUPS["frontend_page"] if kw in question)
    if api_score > 0 and fe_score == 0:
        return "http_api"
    if fe_score > 0 and api_score == 0:
        return "frontend_page"
    if api_score > fe_score:
        return "http_api"
    if fe_score > api_score:
        return "frontend_page"
    return None


def _chunk_scope_score(text: str, scope: str) -> float:
    """chunk 与目标 scope 的匹配分（越高越相关）。"""
    if not text:
        return 0.0
    lower = text.lower()
    preferred = SCOPE_KEYWORD_GROUPS.get(scope, ())
    other_scope = "frontend_page" if scope == "http_api" else "http_api"
    avoided = SCOPE_KEYWORD_GROUPS.get(other_scope, ())

    preferred_hits = sum(1 for kw in preferred if kw.lower() in lower or kw in text)
    avoided_hits = sum(1 for kw in avoided if kw in text)
    return preferred_hits * SCOPE_MATCH_BONUS - avoided_hits * SCOPE_MISMATCH_PENALTY


def _rerank_hits_by_scope(hits: list[dict[str, Any]], question: str) -> list[dict[str, Any]]:
    """
    在向量检索结果上按问题类型二次排序。
    向量距离越小越好；scope 加分用于同批结果内微调顺序。
    """
    scope = _detect_scope(question)
    if not scope or not hits:
        return hits

    def sort_key(hit: dict[str, Any]) -> tuple[float, float]:
        distance = hit.get("distance")
        dist_val = float(distance) if isinstance(distance, (int, float)) else 999.0
        scope_bonus = _chunk_scope_score(hit.get("text") or "", scope)
        return (dist_val - scope_bonus, dist_val)

    return sorted(hits, key=sort_key)


def _build_retrieval_query(question: str, history: list[dict[str, str]] | None = None) -> str:
    """
    构造用于向量检索的 query 文本。

    - 普通问题：直接用用户原问
    - 追问：拼接最近一轮 user+assistant，帮助 embedding 理解指代
    - 来源追问：额外强调「文档名、章节、页码」
    """
    q = question.strip()
    hist = _normalize_history(history)
    parts: list[str] = [q]

    if hist and (_is_followup_question(q) or _is_source_attribution_question(q) or len(q) < 20):
        recent = hist[-2:]
        for turn in recent:
            role_label = "用户" if turn["role"] == "user" else "助手"
            snippet = turn["content"][:400]
            parts.append(f"{role_label}：{snippet}")

    if _is_source_attribution_question(q):
        parts.append("请查找上述内容出自哪份文档、哪一节或哪一页")

    return "\n".join(parts)


def _build_user_prompt(
    question: str,
    context: str,
    *,
    history: list[dict[str, str]] | None = None,
) -> str:
    """构造最终 user 消息：参考资料 + 当前问题；来源追问时附加说明。"""
    lines = [f"参考资料：\n{context}", f"\n用户问题：{question.strip()}"]
    if _is_source_attribution_question(question):
        lines.append(
            "\n说明：用户在追问资料出处，请根据参考资料说明文档名与章节/页码，"
            "不要回答系统架构或数据库来源。"
        )
    return "\n".join(lines)


async def retrieve_context(
    kb_id: str,
    question: str,
    *,
    top_k: int | None = None,
    history: list[dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """
    检索与问题相关的 chunk。

    1. 扩展 query（含历史）→ Ollama embedding
    2. Chroma 向量检索 top_k
    3. 按问题类型重排，减少跨主题 chunk 混入
    """
    k = top_k if top_k is not None else KB_RAG_TOP_K
    retrieval_query = _build_retrieval_query(question, history)
    query_vec = await embed_text(retrieval_query)
    hits = query_kb(kb_id, query_vec, top_k=k)
    return _rerank_hits_by_scope(hits, question)


async def answer_with_rag(
    kb_id: str,
    question: str,
    *,
    top_k: int | None = None,
    history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """
    RAG 问答：检索 + MiniMax 生成。

    参数：
        kb_id: 知识库 ID
        question: 当前用户问题
        top_k: 检索 chunk 数量，默认读 KB_RAG_TOP_K
        history: 最近对话 [{role, content}, ...]，用于多轮理解与检索扩展

    返回：{ answer, citations, hits }
    """
    hist = _normalize_history(history)
    hits = await retrieve_context(kb_id, question, top_k=top_k, history=hist)
    context = _build_context(hits)

    messages: list[dict[str, str]] = [{"role": "system", "content": RAG_SYSTEM_PROMPT}]
    for turn in hist:
        messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append(
        {
            "role": "user",
            "content": _build_user_prompt(question, context, history=hist),
        }
    )

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
