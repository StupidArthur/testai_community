"""AI 早报流水线：Tavily 搜索 → ai_service.client.chat 总结 → 可选落盘。"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.platform.config import AI_NEWS_OUTPUT_DIR
from app.ai_service.client import chat
from app.ai_service.registry import DEFAULT_MODEL_ID
from app.ai_service.news.models import NewsSearchResult
from app.ai_service.news.prompts import DAILY_NEWS_SYSTEM_PROMPT, build_summary_user_message
from app.ai_service.news.tavily import DEFAULT_MAX_RESULTS, search_ai_news
from app.ai_service.news.validate import validate_report_links

log = logging.getLogger("app.ai_service.news.pipeline")

# LLM 总结参数
SUMMARY_TEMPERATURE = 0.1
SUMMARY_MAX_TOKENS = 4096
MAX_AGE_HOURS = 48
OUTPUT_DATE_FORMAT = "%Y-%m-%d"
OUTPUT_FILENAME_TEMPLATE = "{date}-AI-Daily-News.md"
BEIJING_TZ = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class DailyNewsResult:
    """一次早报生成的结果。"""

    markdown: str
    search: NewsSearchResult
    output_path: Path | None
    generated_at: datetime
    invalid_links: tuple[str, ...] = ()


def _default_output_path(output_dir: Path, generated_at: datetime) -> Path:
    """由日期推导 Markdown 文件名。"""
    date_str = generated_at.astimezone(BEIJING_TZ).strftime(OUTPUT_DATE_FORMAT)
    return output_dir / OUTPUT_FILENAME_TEMPLATE.format(date=date_str)


def save_daily_news_markdown(
    markdown: str,
    *,
    output_dir: Path,
    generated_at: datetime | None = None,
) -> Path:
    """将 Markdown 写入 output_dir；文件名带日期标签，避免覆盖历史早报。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = generated_at or datetime.now(BEIJING_TZ)
    path = _default_output_path(output_dir, ts)
    path.write_text(markdown, encoding="utf-8")
    log.info("AI 早报已写入 %s", path)
    return path


async def summarize_news_markdown(
    search: NewsSearchResult,
    *,
    report_date: str,
    model: str = DEFAULT_MODEL_ID,
    temperature: float = SUMMARY_TEMPERATURE,
    max_tokens: int = SUMMARY_MAX_TOKENS,
    max_age_hours: int = MAX_AGE_HOURS,
) -> tuple[str, tuple[str, ...]]:
    """调用 ai_service.client.chat 将搜索原文整理为 Markdown 早报。"""
    if not search.llm_context.strip():
        raise ValueError("搜索原文为空，无法生成早报")

    messages = [
        {"role": "system", "content": DAILY_NEWS_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": build_summary_user_message(
                search,
                report_date=report_date,
                max_age_hours=max_age_hours,
            ),
        },
    ]
    log.info("LLM 总结开始 model=%s", model)
    markdown = await chat(
        messages,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        think=False,
    )
    invalid = tuple(validate_report_links(markdown, search.allowed_urls))
    log.info("LLM 总结完成，长度=%s，链接校验违规=%s", len(markdown), len(invalid))
    return markdown, invalid


async def generate_daily_news(
    *,
    query: str | None = None,
    max_results: int = DEFAULT_MAX_RESULTS,
    output_dir: Path | None = None,
    save_to_file: bool = True,
    model: str = DEFAULT_MODEL_ID,
    temperature: float = SUMMARY_TEMPERATURE,
    max_tokens: int = SUMMARY_MAX_TOKENS,
    max_age_hours: int = MAX_AGE_HOURS,
) -> DailyNewsResult:
    """
    完整早报流程：Tavily 搜索 → chat 总结 → 可选保存 Markdown。

    返回 DailyNewsResult；若搜索无有效内容，markdown 为空字符串且不写文件。
    """
    generated_at = datetime.now(BEIJING_TZ)
    report_date = generated_at.strftime(OUTPUT_DATE_FORMAT)
    target_dir = output_dir or AI_NEWS_OUTPUT_DIR

    search = await search_ai_news(
        query,
        max_results=max_results,
        reference_date=generated_at.date(),
    )
    if not search.llm_context.strip():
        log.warning("Tavily 未返回有效内容")
        return DailyNewsResult(
            markdown="",
            search=search,
            output_path=None,
            generated_at=generated_at,
        )

    markdown, invalid = await summarize_news_markdown(
        search,
        report_date=report_date,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        max_age_hours=max_age_hours,
    )

    output_path: Path | None = None
    if save_to_file and markdown.strip():
        output_path = save_daily_news_markdown(
            markdown,
            output_dir=target_dir,
            generated_at=generated_at,
        )

    return DailyNewsResult(
        markdown=markdown,
        search=search,
        output_path=output_path,
        generated_at=generated_at,
        invalid_links=invalid,
    )


async def _run_default() -> DailyNewsResult:
    """模块默认入口：生成并保存今日早报。"""
    return await generate_daily_news()
