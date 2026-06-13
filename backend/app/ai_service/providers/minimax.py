"""MiniMax OpenAI 兼容 Provider。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import openai

from app.platform.config import MINIMAX_API_KEY, MINIMAX_API_URL

from ..exceptions import LLMNotConfiguredError
from .base import LLMProvider

log = logging.getLogger(__name__)

DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_DELAY_MS = 2000


class MiniMaxProvider(LLMProvider):
    """MiniMax Chat Completions（OpenAI SDK 兼容）。"""

    name = "minimax"

    def __init__(self) -> None:
        self._client: openai.AsyncOpenAI | None = None

    def is_configured(self) -> bool:
        return bool(MINIMAX_API_KEY)

    def _get_client(self) -> openai.AsyncOpenAI:
        if not MINIMAX_API_KEY:
            raise LLMNotConfiguredError("请设置环境变量 MINIMAX_API_KEY")
        if self._client is None:
            self._client = openai.AsyncOpenAI(
                api_key=MINIMAX_API_KEY,
                base_url=MINIMAX_API_URL,
            )
        return self._client

    def chat_extra_body(self, *, think: bool) -> dict[str, Any]:
        # think=False 时开启 reasoning_split，translate audit 等场景使用
        if not think:
            return {"reasoning_split": True}
        return {}

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        think: bool,
        max_retries: int = DEFAULT_MAX_RETRIES,
        base_delay_ms: int = DEFAULT_BASE_DELAY_MS,
    ) -> str:
        client = self._get_client()
        extra_body = self.chat_extra_body(think=think) or None
        last_error: Exception | None = None

        for attempt in range(1, max_retries + 1):
            try:
                completion = await client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    extra_body=extra_body,
                )
                content = completion.choices[0].message.content
                if not content:
                    raise ValueError("AI 返回空结果")
                return content
            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    delay = base_delay_ms * (2 ** (attempt - 1))
                    log.warning(
                        "MiniMax 调用失败，第 %s 次重试: %s，%sms 后重试...",
                        attempt,
                        e,
                        delay,
                    )
                    await asyncio.sleep(delay / 1000)

        raise RuntimeError(
            f"MiniMax 调用彻底失败，已重试 {max_retries} 次: {last_error}"
        )
