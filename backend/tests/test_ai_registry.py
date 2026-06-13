"""ai_service ModelRegistry 与 Provider 路由测试。"""

from app.ai_service.registry import (
    DEFAULT_MODEL_ID,
    resolve_model,
    list_models,
)
from app.platform.config import MINIMAX_MODEL


class TestModelRegistry:
    def test_default_model_id(self):
        provider, model_name, supports_think = resolve_model(None)
        assert provider.name == "minimax"
        assert model_name == MINIMAX_MODEL
        assert supports_think is True

    def test_platform_model_id(self):
        provider, model_name, _ = resolve_model(DEFAULT_MODEL_ID)
        assert provider.name == "minimax"
        assert model_name == MINIMAX_MODEL

    def test_vendor_model_name_backward_compat(self):
        custom = "MiniMax-M2.7-highspeed"
        provider, model_name, _ = resolve_model(custom)
        assert provider.name == "minimax"
        assert model_name == custom

    def test_list_models_not_empty(self):
        models = list_models()
        assert len(models) >= 1
        assert models[0].model_id == DEFAULT_MODEL_ID
