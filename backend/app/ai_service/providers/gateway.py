"""LLM Gateway Provider（OpenAI 兼容接口，单并发）。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.platform.config import LLM_GATEWAY_URL, LLM_GATEWAY_API_KEY, LLM_GATEWAY_MODEL

from ..exceptions import LLMNotConfiguredError
from .base import LLMProvider

log = logging.getLogger(__name__)

DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_DELAY_MS = 2000


class GatewayProvider(LLMProvider):
    """LLM Gateway（OpenAI 兼容接口，单并发）。"""

    name = "gateway"

    def __init__(self) -> None:
        self._semaphore = asyncio.Semaphore(1)
        self._client: httpx.AsyncClient | None = None

    def is_configured(self) -> bool:
        return bool(LLM_GATEWAY_URL)

    def _get_http_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(120.0))
        return self._client

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
        if not LLM_GATEWAY_URL:
            raise LLMNotConfiguredError("请设置环境变量 LLM_GATEWAY_URL")

        async with self._semaphore:  # 单并发，不排队
            client = self._get_http_client()
            payload: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            headers = {"Content-Type": "application/json"}
            if LLM_GATEWAY_API_KEY:
                headers["Authorization"] = f"Bearer {LLM_GATEWAY_API_KEY}"

            last_error: Exception | None = None
            for attempt in range(1, max_retries + 1):
                try:
                    resp = await client.post(LLM_GATEWAY_URL, json=payload, headers=headers)
                    resp.raise_for_status()
                    data = resp.json()
                    choices = data.get("choices", [])
                    if not choices:
                        raise ValueError("AI 返回空结果（无 choices）")
                    content = choices[0].get("message", {}).get("content", "")
                    if not content:
                        raise ValueError("AI 返回空结果（content 为空）")
                    return content
                except Exception as e:
                    last_error = e
                    if attempt < max_retries:
                        delay = base_delay_ms * (2 ** (attempt - 1))
                        log.warning(
                            "Gateway 调用失败，第 %s 次重试: %s，%sms 后重试...",
                            attempt, e, delay,
                        )
                        await asyncio.sleep(delay / 1000)

            raise RuntimeError(
                f"Gateway 调用彻底失败，已重试 {max_retries} 次: {last_error}"
            )