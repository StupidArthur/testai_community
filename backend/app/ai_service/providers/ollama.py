"""
Ollama 本地模型 Provider：Embedding 与多模态视觉（Qwen2.5-VL）。

通过 HTTP 调用 Ollama API；API Key 可选（本地部署通常留空）。
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any

import httpx

from app.platform.config import (
    OLLAMA_API_KEY,
    OLLAMA_BASE_URL,
    OLLAMA_EMBED_MODEL,
    OLLAMA_VL_MODEL,
    OLLAMA_VISION_PROMPT,
)

from ..exceptions import LLMNotConfiguredError

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SEC = 120.0
EMBED_TIMEOUT_SEC = 60.0


class OllamaProvider:
    """Ollama 本地 API 封装（Embedding + Vision）。"""

    name = "ollama"

    def __init__(self) -> None:
        self._base_url = OLLAMA_BASE_URL.rstrip("/")

    def is_configured(self) -> bool:
        """Ollama 为本地服务，仅需 base_url 非空即可尝试调用。"""
        return bool(self._base_url)

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if OLLAMA_API_KEY:
            headers["Authorization"] = f"Bearer {OLLAMA_API_KEY}"
        return headers

    async def embed_text(self, text: str, *, model: str | None = None) -> list[float]:
        """
        单条文本向量化。

        :param text: 待嵌入文本
        :param model: 覆盖默认 OLLAMA_EMBED_MODEL
        :return: 浮点向量
        """
        if not self.is_configured():
            raise LLMNotConfiguredError("请设置 OLLAMA_BASE_URL 并启动 Ollama 服务")
        payload = {
            "model": model or OLLAMA_EMBED_MODEL,
            "prompt": text,
        }
        async with httpx.AsyncClient(timeout=EMBED_TIMEOUT_SEC) as client:
            resp = await client.post(
                f"{self._base_url}/api/embeddings",
                json=payload,
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()
        embedding = data.get("embedding")
        if not isinstance(embedding, list) or not embedding:
            raise RuntimeError(f"Ollama embedding 返回异常: {data}")
        return [float(x) for x in embedding]

    async def embed_texts(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
        """批量向量化（逐条调用，避免部分模型不支持 batch）。"""
        results: list[list[float]] = []
        for text in texts:
            results.append(await self.embed_text(text, model=model))
        return results

    async def describe_image(
        self,
        image_path: Path,
        *,
        prompt: str | None = None,
        model: str | None = None,
    ) -> str:
        """
        使用多模态模型描述图片/流程图内容。

        :param image_path: 本地图片路径
        :param prompt: 自定义提示词
        :param model: 覆盖默认 OLLAMA_VL_MODEL
        :return: 模型生成的文字描述
        """
        if not self.is_configured():
            raise LLMNotConfiguredError("请设置 OLLAMA_BASE_URL 并启动 Ollama 服务")
        if not image_path.is_file():
            raise FileNotFoundError(f"图片不存在: {image_path}")

        image_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
        user_prompt = prompt or OLLAMA_VISION_PROMPT
        payload: dict[str, Any] = {
            "model": model or OLLAMA_VL_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": user_prompt,
                    "images": [image_b64],
                }
            ],
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SEC) as client:
            resp = await client.post(
                f"{self._base_url}/api/chat",
                json=payload,
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()
        message = data.get("message") or {}
        content = message.get("content", "")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError(f"Ollama vision 返回空内容: {data}")
        return content.strip()


_ollama_provider: OllamaProvider | None = None


def get_ollama_provider() -> OllamaProvider:
    """获取 Ollama Provider 单例。"""
    global _ollama_provider
    if _ollama_provider is None:
        _ollama_provider = OllamaProvider()
    return _ollama_provider
