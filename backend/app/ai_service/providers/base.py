"""LLM Provider 抽象：各厂商实现统一 chat 接口。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class LLMProvider(ABC):
    """单个 LLM 厂商/接入点的调用封装。"""

    name: str

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        think: bool,
        max_retries: int,
        base_delay_ms: int,
    ) -> str:
        """发送 messages 并返回 assistant 文本。"""

    @abstractmethod
    def is_configured(self) -> bool:
        """当前 Provider 是否已配置可用凭证。"""

    def chat_extra_body(self, *, think: bool) -> dict[str, Any]:
        """厂商特有请求体扩展；子类按需覆盖。"""
        return {}
