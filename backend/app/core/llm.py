"""共享 LLM 客户端，统一 skill_hub 和 translate 的调用方式。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import openai

from app.core.config import MINIMAX_API_KEY, MINIMAX_API_URL, MINIMAX_MODEL

DEFAULT_MODEL = MINIMAX_MODEL
DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_DELAY_MS = 2000

_client: openai.AsyncOpenAI | None = None


def _get_client() -> openai.AsyncOpenAI:
    global _client
    if _client is None:
        _client = openai.AsyncOpenAI(
            api_key=MINIMAX_API_KEY,
            base_url=MINIMAX_API_URL,
        )
    return _client


async def chat(
    messages: list[dict[str, str]],
    *,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.2,
    max_tokens: int = 4096,
    think: bool = True,
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay_ms: int = DEFAULT_BASE_DELAY_MS,
) -> str:
    client = _get_client()
    last_error = None

    extra_body: dict[str, Any] = {}
    if not think:
        extra_body["reasoning_split"] = True

    for attempt in range(1, max_retries + 1):
        try:
            completion = await client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                extra_body=extra_body or None,
            )
            content = completion.choices[0].message.content
            if not content:
                raise ValueError("AI 返回空结果")
            return content
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                delay = base_delay_ms * (2 ** (attempt - 1))
                logging.getLogger(__name__).warning(
                    f"LLM 调用失败，第 {attempt} 次重试: {e}，{delay}ms 后重试..."
                )
                await asyncio.sleep(delay / 1000)

    raise RuntimeError(f"LLM 调用彻底失败，已重试 {max_retries} 次: {last_error}")
