"""
回答生成：仅在用户提问时调用 LLM。

规则：
1. 只能使用参考资料
2. 不添加资料外内容
3. 无答案则固定话术
4. 直接引用原文，不要改写
回答后校验关键实体；若有资料外实体则丢弃回答，返回 chunk 原文。
"""

from __future__ import annotations

import logging
import re

import httpx

from rag_pipeline.config import OLLAMA_BASE_URL, OLLAMA_CHAT_MODEL
from rag_pipeline.models.schemas import Chunk

log = logging.getLogger(__name__)

ANSWER_UNAVAILABLE = "根据现有知识库无法回答"

_PROMPT_TEMPLATE = """你是一个回答助手。根据以下参考资料回答用户问题。
规则：
1. 只能使用参考资料中的信息
2. 不要添加任何参考资料以外的内容
3. 如果参考资料中没有答案，回答"根据现有知识库无法回答"
4. 直接引用原文，不要改写
5. 如果参考资料中包含多个并列项（如多个层级、多个模块），必须列出所有提到的项，不得遗漏。如果资料中只提到部分项，回答时如实说明「资料中提到了以下X个」，不要说「仅详细说明了这一层」这种暗示资料不完整的话

参考资料：
{refs}

用户问题：
{question}
"""

_RE_ENTITY = re.compile(r"[\u4e00-\u9fff]{2,12}|[A-Z]{2,}|\d+-[A-Z]+-\d+")


def build_prompt(question: str, chunks: list[Chunk]) -> str:
    """按固定模板拼装 prompt。"""
    refs = "\n\n".join(
        f"[{c.chunk_id}] {c.chapter_path}\n{c.raw_text}" for c in chunks
    )
    return _PROMPT_TEMPLATE.format(refs=refs or "(无)", question=question)


def _chat_ollama(prompt: str, *, base_url: str, model: str, timeout: float = 120.0) -> str:
    url = f"{base_url.rstrip('/')}/api/chat"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0.0},
    }
    with httpx.Client(timeout=timeout) as client:
        r = client.post(url, json=payload)
        r.raise_for_status()
        data = r.json()
    msg = data.get("message") or {}
    return str(msg.get("content") or "").strip()


def extract_answer_entities(answer: str) -> list[str]:
    """从回答中抽取用于校验的关键实体。"""
    return list(dict.fromkeys(_RE_ENTITY.findall(answer or "")))


def validate_answer_entities(answer: str, chunks: list[Chunk]) -> bool:
    """
    检查回答中的关键实体是否都在检索到的 chunk 里出现过。
    停用词级短词跳过；若回答为固定无法回答话术则直接通过。
    """
    if not answer or answer.strip() == ANSWER_UNAVAILABLE:
        return True
    blob = re.sub(r"\s+", "", "\n".join(c.raw_text for c in chunks))
    for ent in extract_answer_entities(answer):
        if len(ent) < 2:
            continue
        # 常见虚词跳过
        if ent in {"根据", "现有", "知识库", "无法", "回答", "参考", "资料", "用户", "问题"}:
            continue
        if re.sub(r"\s+", "", ent) not in blob:
            return False
    return True


def fallback_raw_answer(chunks: list[Chunk]) -> str:
    """实体校验失败时直接返回 chunk 原文。"""
    if not chunks:
        return ANSWER_UNAVAILABLE
    return "\n\n".join(c.raw_text for c in chunks)


def generate_answer(
    question: str,
    chunks: list[Chunk],
    *,
    base_url: str = OLLAMA_BASE_URL,
    model: str = OLLAMA_CHAT_MODEL,
    chat_fn=None,
) -> str:
    """生成回答并做实体校验。"""
    if not chunks:
        return ANSWER_UNAVAILABLE
    prompt = build_prompt(question, chunks)
    try:
        if chat_fn is not None:
            answer = chat_fn(prompt)
        else:
            answer = _chat_ollama(prompt, base_url=base_url, model=model)
    except Exception as exc:  # noqa: BLE001
        log.warning("chat failed: %s; fallback to raw chunks", exc)
        return fallback_raw_answer(chunks)

    answer = (answer or "").strip()
    if not answer:
        return fallback_raw_answer(chunks)
    if not validate_answer_entities(answer, chunks):
        log.info("entity validation failed; return raw chunks")
        return fallback_raw_answer(chunks)
    return answer
