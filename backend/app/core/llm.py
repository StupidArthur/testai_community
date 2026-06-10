"""共享 LLM 客户端，统一 skill_hub 和 translate 的调用方式。"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import httpx
import openai

from app.core.config import MINIMAX_API_KEY, MINIMAX_API_URL

DEFAULT_MODEL = "MiniMax-M2.7-highspeed"
DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_DELAY_MS = 2000


def _to_openai_base_url(url: str) -> str:
    if "/text/chatcompletion_v2" in url:
        return url.rsplit("/text/chatcompletion_v2", 1)[0]
    if url.endswith("/chat/completions"):
        return url.rsplit("/chat/completions", 1)[0]
    return url.rstrip("/")


def create_openai_client(
    *,
    base_url: str | None = None,
    api_key: str | None = None,
) -> openai.AsyncOpenAI:
    return openai.AsyncOpenAI(
        api_key=api_key or MINIMAX_API_KEY,
        base_url=base_url or _to_openai_base_url(MINIMAX_API_URL),
    )


async def chat(
    messages: list[dict[str, str]],
    *,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.3,
    max_tokens: int = 4096,
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay_ms: int = DEFAULT_BASE_DELAY_MS,
    client: openai.AsyncOpenAI | None = None,
) -> str:
    _client = client or create_openai_client()
    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            completion = await _client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            content = completion.choices[0].message.content
            if not content:
                raise ValueError("AI 返回空结果")
            return content
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                delay = base_delay_ms * (2 ** (attempt - 1))
                logging.getLogger(__name__).warning(
                    f"LLM 调用失败，第 {attempt} 次重试: {e}，{delay}ms 后重试..."
                )
                await asyncio.sleep(delay / 1000)

    raise RuntimeError(f"LLM 调用彻底失败，已重试 {max_retries} 次: {last_error}")


async def vision(
    image_base64: str,
    prompt: str,
    *,
    media_type: str = "image/jpeg",
    max_tokens: int = 1000,
    model: str = "MiniMax-M3",
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay_ms: int = DEFAULT_BASE_DELAY_MS,
) -> str:
    vision_url = "https://api.minimaxi.com/anthropic/v1/messages"

    for attempt in range(1, max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=120) as http:
                resp = await http.post(
                    vision_url,
                    headers={
                        "Content-Type": "application/json",
                        "x-api-key": MINIMAX_API_KEY,
                        "anthropic-version": "2023-06-01",
                    },
                    json={
                        "model": model,
                        "max_tokens": max_tokens,
                        "messages": [{
                            "role": "user",
                            "content": [
                                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_base64}},
                                {"type": "text", "text": prompt},
                            ],
                        }],
                    },
                )
                resp.raise_for_status()
                result = resp.json()

            if "error" in result:
                raise ValueError(f"视觉 API 错误: {result['error']}")

            text_content = next(
                (c for c in result.get("content", []) if c.get("type") == "text"),
                None,
            )
            if not text_content or not text_content.get("text"):
                raise ValueError("视觉模型返回空结果")
            return text_content["text"]
        except Exception as e:
            if attempt < max_retries:
                delay = base_delay_ms * (2 ** (attempt - 1))
                await asyncio.sleep(delay / 1000)
            else:
                raise

    raise RuntimeError("视觉模型调用彻底失败")


async def ping(timeout_ms: int = 3000) -> str:
    _client = create_openai_client()
    controller = httpx.AsyncClient(timeout=timeout_ms / 1000)
    try:
        async with controller:
            resp = await controller.post(
                f"{str(_client.base_url).rstrip('/')}/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {_client.api_key}",
                },
                json={
                    "model": DEFAULT_MODEL,
                    "messages": [{"role": "user", "content": "你好"}],
                    "max_tokens": 32,
                    "temperature": 0,
                },
            )
            resp.raise_for_status()
            result = resp.json()
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        if not content:
            raise ValueError("AI 返回空结果")
        return content
    except Exception as e:
        raise ValueError("LLM 调用出错，请确认 config 或者网络。") from e


def clean_markdown_fence(text: str) -> str:
    if not text:
        return ""

    trimmed = text.strip()

    trimmed = re.sub(r"<thinking>[\s\S]*?</thinking>", "", trimmed, flags=re.IGNORECASE)
    trimmed = re.sub(r"^```[\w]*\s*\n?", "", trimmed)
    trimmed = re.sub(r"\n?```\s*$", "", trimmed)

    return trimmed.strip()


def extract_first_json_object(text: str) -> str | None:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    return text[start : end + 1]


def parse_json_from_llm_reply(text: str) -> dict[str, Any]:
    import json

    cleaned = clean_markdown_fence(text)

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    extracted = extract_first_json_object(cleaned)
    if extracted:
        try:
            parsed = json.loads(extracted)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    raise ValueError("无法从 LLM 输出解析 JSON 对象")