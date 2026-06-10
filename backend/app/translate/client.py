"""translate LLM 客户端 —— 委托给 app.core.llm 共享模块。"""

from __future__ import annotations

from typing import Any

from app.core.llm import (
    DEFAULT_MODEL,
    chat as _chat,
    clean_markdown_fence,
    create_openai_client,
    extract_first_json_object,
    parse_json_from_llm_reply,
    ping as _ping,
    vision as _vision,
)
from .config import (
    LLM_BASE_DELAY_MS,
    LLM_MAX_RETRIES,
)


class LLMClient:
    def __init__(self, base_url: str, api_key: str, model: str):
        self._client = create_openai_client(base_url=base_url, api_key=api_key)
        self._model = model or DEFAULT_MODEL
        self._max_retries = LLM_MAX_RETRIES
        self._base_delay_ms = LLM_BASE_DELAY_MS

    @classmethod
    def from_config(cls) -> LLMClient:
        from .config import load_ai_config
        config = load_ai_config()
        from app.core.llm import _to_openai_base_url
        base_url = _to_openai_base_url(config.get("baseUrl", ""))
        return cls(
            base_url=base_url,
            api_key=config.get("apiKey", ""),
            model=config.get("model", DEFAULT_MODEL),
        )

    async def call_chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 2000,
        model: str | None = None,
    ) -> str:
        return await _chat(
            messages,
            model=model or self._model,
            temperature=temperature,
            max_tokens=max_tokens,
            max_retries=self._max_retries,
            base_delay_ms=self._base_delay_ms,
            client=self._client,
        )

    async def call_vision(
        self,
        image_base64: str,
        prompt: str,
        *,
        media_type: str = "image/jpeg",
        max_tokens: int = 1000,
        model: str | None = None,
    ) -> str:
        return await _vision(
            image_base64,
            prompt,
            media_type=media_type,
            max_tokens=max_tokens,
            model=model or "MiniMax-M3",
            max_retries=self._max_retries,
            base_delay_ms=self._base_delay_ms,
        )

    async def ping(self, timeout_ms: int = 3000) -> str:
        return await _ping(timeout_ms=timeout_ms)
