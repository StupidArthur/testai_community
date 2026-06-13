"""LLM 客户端：经 ModelRegistry 路由到 Provider。"""

from __future__ import annotations

from app.platform.config import MINIMAX_MODEL

from .exceptions import LLMNotConfiguredError
from .registry import DEFAULT_MODEL_ID, resolve_model

DEFAULT_MODEL = MINIMAX_MODEL
DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_DELAY_MS = 2000


async def chat(
    messages: list[dict[str, str]],
    *,
    model: str = DEFAULT_MODEL_ID,
    temperature: float = 0.2,
    max_tokens: int = 4096,
    think: bool = True,
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay_ms: int = DEFAULT_BASE_DELAY_MS,
) -> str:
    """
    向 LLM 发送 messages，返回 assistant 文本内容。

    model 可为 platform model_id（如 minimax-default）或厂商模型名（向后兼容）。
    """
    provider, provider_model, _supports_think = resolve_model(model)
    if not provider.is_configured():
        raise LLMNotConfiguredError("请设置环境变量 MINIMAX_API_KEY")
    return await provider.chat(
        messages,
        model=provider_model,
        temperature=temperature,
        max_tokens=max_tokens,
        think=think,
        max_retries=max_retries,
        base_delay_ms=base_delay_ms,
    )
