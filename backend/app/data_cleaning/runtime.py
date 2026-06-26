"""
数据清洗运行时探测（Ollama 可用性等）。
"""

from __future__ import annotations

import logging
import time

import httpx

from app.platform.config import OLLAMA_BASE_URL

log = logging.getLogger(__name__)

_OLLAMA_PROBE_TTL_SEC = 30.0
_ollama_last_probe = 0.0
_ollama_available: bool | None = None


async def ollama_available(*, force: bool = False) -> bool:
    """探测 Ollama 是否可达；失败时短时缓存，避免每段等待长超时。"""
    global _ollama_last_probe, _ollama_available
    now = time.monotonic()
    if not force and _ollama_available is not None and now - _ollama_last_probe < _OLLAMA_PROBE_TTL_SEC:
        return _ollama_available

    ok = False
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{OLLAMA_BASE_URL.rstrip('/')}/api/tags")
            ok = resp.status_code == 200
    except Exception as exc:
        log.debug("Ollama 不可用: %s", exc)

    _ollama_available = ok
    _ollama_last_probe = now
    return ok
