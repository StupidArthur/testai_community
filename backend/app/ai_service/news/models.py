"""AI 早报搜索与流水线数据结构。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NewsSearchItem:
    """Tavily 单条搜索结果。"""

    index: int
    title: str
    content: str
    url: str
    published_date: str = ""


@dataclass(frozen=True)
class NewsSearchResult:
    """一次 Tavily 搜索的结构化结果。"""

    query: str
    items: tuple[NewsSearchItem, ...]
    allowed_urls: frozenset[str]
    llm_context: str
