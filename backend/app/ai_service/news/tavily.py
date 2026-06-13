"""Tavily 搜索：抓取 AI 行业最新资讯原文。"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.platform.config import TAVILY_API_KEY, TAVILY_SEARCH_URL
from app.ai_service.exceptions import NewsSearchError, TavilyNotConfiguredError
from app.ai_service.news.models import NewsSearchItem, NewsSearchResult

log = logging.getLogger("app.ai_service.news.tavily")

BEIJING_TZ = ZoneInfo("Asia/Shanghai")

DEFAULT_MAX_RESULTS = 8
TAVILY_TIMEOUT_SEC = 30.0
TAVILY_SEARCH_DEPTH = "advanced"
# Tavily days：限制搜索结果时间范围（天）
TAVILY_DAYS = 1
TAVILY_TOPIC = "news"


def build_search_query(reference_date: date | None = None) -> str:
    """按报告日期生成搜索词，减少年度盘点类旧文。"""
    day = reference_date or datetime.now(BEIJING_TZ).date()
    return (
        f"AI LLM large language model Coding Agent framework open source release "
        f"breaking news {day.isoformat()}"
    )


def _parse_items(results: list[dict[str, Any]]) -> tuple[NewsSearchItem, ...]:
    items: list[NewsSearchItem] = []
    for idx, row in enumerate(results, start=1):
        url = (row.get("url") or "").strip()
        if not url:
            continue
        items.append(
            NewsSearchItem(
                index=idx,
                title=(row.get("title") or "").strip(),
                content=(row.get("content") or "").strip(),
                url=url,
                published_date=(row.get("published_date") or row.get("publishedDate") or "").strip(),
            )
        )
    return tuple(items)


def _build_llm_context(items: tuple[NewsSearchItem, ...]) -> str:
    blocks: list[str] = []
    for item in items:
        date_line = f"发布日期: {item.published_date}\n" if item.published_date else ""
        blocks.append(
            f"[{item.index}] 标题: {item.title}\n"
            f"{date_line}"
            f"链接: {item.url}\n"
            f"内容: {item.content}\n"
        )
    return "\n".join(blocks)


async def search_ai_news(
    query: str | None = None,
    *,
    max_results: int = DEFAULT_MAX_RESULTS,
    search_depth: str = TAVILY_SEARCH_DEPTH,
    days: int = TAVILY_DAYS,
    reference_date: date | None = None,
) -> NewsSearchResult:
    """
    调用 Tavily Search API，返回结构化结果 + LLM 上下文。

    未配置 TAVILY_API_KEY 时抛出 TavilyNotConfiguredError。
    """
    if not TAVILY_API_KEY:
        raise TavilyNotConfiguredError("请设置环境变量 TAVILY_API_KEY")

    final_query = query or build_search_query(reference_date)
    payload: dict[str, Any] = {
        "api_key": TAVILY_API_KEY,
        "query": final_query,
        "search_depth": search_depth,
        "include_answer": False,
        "max_results": max_results,
        "days": days,
        "topic": TAVILY_TOPIC,
    }

    log.info(
        "Tavily 搜索开始 query=%r max_results=%s days=%s",
        final_query,
        max_results,
        days,
    )
    try:
        async with httpx.AsyncClient(timeout=TAVILY_TIMEOUT_SEC) as client:
            response = await client.post(TAVILY_SEARCH_URL, json=payload)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        raise NewsSearchError(f"Tavily HTTP 请求失败: {exc}") from exc

    results = data.get("results")
    if not isinstance(results, list):
        raise NewsSearchError(f"Tavily 返回格式异常: {data!r}")

    items = _parse_items(results)
    allowed = frozenset(item.url for item in items if item.url)
    context = _build_llm_context(items)
    log.info("Tavily 搜索完成，条目数=%s，白名单链接=%s", len(items), len(allowed))

    return NewsSearchResult(
        query=final_query,
        items=items,
        allowed_urls=allowed,
        llm_context=context,
    )
