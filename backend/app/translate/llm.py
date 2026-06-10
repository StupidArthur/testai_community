"""translate LLM 客户端工厂 —— 委托给 app.core.llm 共享模块。"""

from __future__ import annotations

from app.core.llm import _to_openai_base_url, create_openai_client
from app.core.config import MINIMAX_API_KEY, MINIMAX_API_URL
from .client import LLMClient
from .config import DEFAULT_MODEL


def build_client() -> LLMClient:
    return LLMClient(
        base_url=_to_openai_base_url(MINIMAX_API_URL),
        api_key=MINIMAX_API_KEY,
        model=DEFAULT_MODEL,
    )
