"""ai_service.news 单元测试。"""

from datetime import date, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from app.ai_service.exceptions import TavilyNotConfiguredError
from app.ai_service.news.models import NewsSearchItem, NewsSearchResult
from app.ai_service.news.pipeline import (
    generate_daily_news,
    save_daily_news_markdown,
    summarize_news_markdown,
)
from app.ai_service.news.tavily import build_search_query, search_ai_news
from app.ai_service.news.validate import validate_report_links


def _sample_search() -> NewsSearchResult:
    items = (
        NewsSearchItem(
            index=1,
            title="Test",
            content="body",
            url="https://example.com/article",
            published_date="2026-06-13",
        ),
    )
    return NewsSearchResult(
        query="test",
        items=items,
        allowed_urls=frozenset({"https://example.com/article"}),
        llm_context="[1] 标题: Test\n链接: https://example.com/article\n内容: body\n",
    )


SAMPLE_MD = (
    "# 🌍 全球 AI 与 Agent 极简早报\n\n"
    "[Test](https://example.com/article)"
)


@pytest.mark.asyncio
async def test_search_ai_news_requires_tavily_key():
    with patch("app.ai_service.news.tavily.TAVILY_API_KEY", ""):
        with pytest.raises(TavilyNotConfiguredError):
            await search_ai_news()


@pytest.mark.asyncio
async def test_search_ai_news_structured_result():
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "results": [
            {
                "title": "A",
                "content": "alpha",
                "url": "https://a.test/p/1",
                "published_date": "2026-06-13",
            },
        ]
    }

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.ai_service.news.tavily.TAVILY_API_KEY", "test-key"):
        with patch("app.ai_service.news.tavily.httpx.AsyncClient", return_value=mock_client):
            result = await search_ai_news("test query", max_results=1)

    assert result.items[0].url == "https://a.test/p/1"
    assert "https://a.test/p/1" in result.allowed_urls
    assert "标题: A" in result.llm_context
    mock_client.post.assert_awaited_once()
    payload = mock_client.post.await_args.kwargs["json"]
    assert payload["days"] == 1
    assert payload["topic"] == "news"


def test_build_search_query_includes_date():
    q = build_search_query(date(2026, 6, 13))
    assert "2026-06-13" in q


@pytest.mark.asyncio
async def test_summarize_news_markdown_calls_chat():
    search = _sample_search()
    with patch("app.ai_service.news.pipeline.chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = SAMPLE_MD
        md, invalid = await summarize_news_markdown(search, report_date="2026-06-13")

    assert md == SAMPLE_MD
    assert invalid == ()
    mock_chat.assert_awaited_once()
    user_content = mock_chat.await_args.args[0][1]["content"]
    assert "允许链接白名单" in user_content
    assert "https://example.com/article" in user_content
    assert mock_chat.await_args.kwargs["think"] is False


def test_validate_report_links():
    search = _sample_search()
    assert validate_report_links(SAMPLE_MD, search.allowed_urls) == []
    bad = " [x](https://evil.test) "
    assert validate_report_links(bad, search.allowed_urls) == ["https://evil.test"]


@pytest.mark.asyncio
async def test_generate_daily_news_pipeline(tmp_path: Path):
    search = _sample_search()
    with patch("app.ai_service.news.pipeline.search_ai_news", new_callable=AsyncMock) as mock_search:
        with patch("app.ai_service.news.pipeline.chat", new_callable=AsyncMock) as mock_chat:
            mock_search.return_value = search
            mock_chat.return_value = SAMPLE_MD

            result = await generate_daily_news(
                output_dir=tmp_path,
                save_to_file=True,
            )

    assert result.markdown == SAMPLE_MD
    assert result.output_path is not None
    assert result.output_path.exists()


def test_save_daily_news_markdown_filename(tmp_path: Path):
    ts = datetime(2026, 6, 13, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    path = save_daily_news_markdown(
        SAMPLE_MD,
        output_dir=tmp_path,
        generated_at=ts,
    )
    assert path.name == "2026-06-13-AI-Daily-News.md"
