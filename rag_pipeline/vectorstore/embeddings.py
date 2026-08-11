"""
Embedding 客户端：调用现有 Ollama embedding 接口。

入库阶段仅做向量化，不生成任何文本内容。
"""

from __future__ import annotations

import logging
from typing import Callable

import httpx

from rag_pipeline.config import OLLAMA_BASE_URL, OLLAMA_EMBED_MODEL

log = logging.getLogger(__name__)

EmbedFn = Callable[[list[str]], list[list[float]]]


def embed_texts(
    texts: list[str],
    *,
    base_url: str = OLLAMA_BASE_URL,
    model: str = OLLAMA_EMBED_MODEL,
    timeout: float = 120.0,
) -> list[list[float]]:
    """批量向量化；优先 /api/embed，失败回退 /api/embeddings。"""
    if not texts:
        return []
    base = base_url.rstrip("/")
    vectors: list[list[float]] = []
    with httpx.Client(timeout=timeout) as client:
        for text in texts:
            # 新接口
            r = client.post(f"{base}/api/embed", json={"model": model, "input": text})
            if r.status_code == 404:
                r = client.post(
                    f"{base}/api/embeddings",
                    json={"model": model, "prompt": text},
                )
            r.raise_for_status()
            data = r.json()
            if "embeddings" in data:
                emb = data["embeddings"]
                vectors.append(emb[0] if emb and isinstance(emb[0], list) else emb)
            elif "embedding" in data:
                vectors.append(list(data["embedding"]))
            else:
                raise RuntimeError(f"unexpected embed response keys: {list(data.keys())}")
    return vectors


def hash_embed_texts(texts: list[str], *, dim: int = 64) -> list[list[float]]:
    """
    无 Ollama 时的确定性伪向量（仅供单测/离线去重占位）。
    不用于生产问答质量评估。
    """
    import hashlib
    import struct

    out: list[list[float]] = []
    for t in texts:
        h = hashlib.sha256(t.encode("utf-8")).digest()
        vals: list[float] = []
        while len(vals) < dim:
            h = hashlib.sha256(h).digest()
            for i in range(0, len(h), 4):
                if len(vals) >= dim:
                    break
                vals.append(struct.unpack("!i", h[i : i + 4])[0] / 2**31)
        # L2 normalize
        norm = sum(v * v for v in vals) ** 0.5 or 1.0
        out.append([v / norm for v in vals])
    return out
