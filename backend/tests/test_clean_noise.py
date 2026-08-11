"""规则删噪与零 LLM 清洗路径冒烟。"""

from __future__ import annotations

from app.data_cleaning.config import CLEAN_USE_LLM_ESSENCE
from app.data_cleaning.noise import clean_noise


def test_clean_use_llm_essence_default_off() -> None:
    assert CLEAN_USE_LLM_ESSENCE is False


def test_clean_noise_keeps_body_drops_image() -> None:
    src = "前文\n\n![x](a.png){width=\"1in\" height=\"1in\"}\n\n后文句。"
    out = clean_noise(src)
    assert "前文" in out and "后文句。" in out
    assert "![" not in out
    assert "width=" not in out
