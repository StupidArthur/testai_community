"""模型注册表：platform model_id → Provider + 厂商模型名。"""

from __future__ import annotations

from dataclasses import dataclass

from app.platform.config import MINIMAX_MODEL

from .providers.base import LLMProvider
from .providers.minimax import MiniMaxProvider

# 默认平台模型 ID（chat 未指定 model 时使用）
DEFAULT_MODEL_ID = "minimax-default"

_providers: dict[str, LLMProvider] = {
    "minimax": MiniMaxProvider(),
}


@dataclass(frozen=True)
class ModelSpec:
    """平台侧模型描述。"""

    model_id: str
    provider_name: str
    provider_model: str
    supports_think: bool = True


# 已注册平台模型；新增厂商/模型在此追加
MODELS: tuple[ModelSpec, ...] = (
    ModelSpec(
        model_id=DEFAULT_MODEL_ID,
        provider_name="minimax",
        provider_model=MINIMAX_MODEL,
        supports_think=True,
    ),
)

_MODEL_BY_ID: dict[str, ModelSpec] = {m.model_id: m for m in MODELS}


def get_provider(name: str) -> LLMProvider:
    """按 provider 名获取实例。"""
    provider = _providers.get(name)
    if provider is None:
        raise ValueError(f"未知 LLM Provider: {name}")
    return provider


def resolve_model(model: str | None) -> tuple[LLMProvider, str, bool]:
    """
    解析 chat 的 model 参数。

    - None / 空：使用 DEFAULT_MODEL_ID
    - 命中 platform model_id：走注册表
    - 否则：视为 MiniMax 厂商模型名（向后兼容 MINIMAX_MODEL 直传）
    """
    model_key = (model or DEFAULT_MODEL_ID).strip()
    spec = _MODEL_BY_ID.get(model_key)
    if spec is not None:
        return get_provider(spec.provider_name), spec.provider_model, spec.supports_think

    # 向后兼容：调用方传入 MINIMAX_MODEL 等厂商模型名
    return get_provider("minimax"), model_key, True


def list_models() -> list[ModelSpec]:
    """返回已注册平台模型列表（供将来 AI 控制台使用）。"""
    return list(MODELS)
