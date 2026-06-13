"""早报 Markdown 链接校验（对照 Tavily 白名单）。"""

from __future__ import annotations

import logging
import re

log = logging.getLogger("app.ai_service.news.validate")

# Markdown 链接 [text](url)
_MD_LINK_PATTERN = re.compile(r"\]\((https?://[^)\s]+)\)")


def find_markdown_urls(markdown: str) -> set[str]:
    """提取 Markdown 中所有 http(s) 链接。"""
    return set(_MD_LINK_PATTERN.findall(markdown))


def validate_report_links(markdown: str, allowed_urls: frozenset[str]) -> list[str]:
    """
    检查正文链接是否均在白名单内。

    返回违规 URL 列表；空列表表示通过。
    """
    used = find_markdown_urls(markdown)
    if not allowed_urls:
        return sorted(used)
    invalid = sorted(url for url in used if url not in allowed_urls)
    if invalid:
        log.warning("早报含非白名单链接 %s 条: %s", len(invalid), invalid[:5])
    return invalid
