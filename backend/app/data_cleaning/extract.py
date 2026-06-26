"""
LLM 提炼精华与锚点候选。
"""

from __future__ import annotations

import logging
from typing import Any

from app.ai_service.client import chat
from app.data_cleaning.utils import extract_json_object

log = logging.getLogger(__name__)

# 思维链 / 模板类段落：原文已结构化，跳过 LLM 提炼以提速
_THINKING_CHAIN_MARKERS = (
    "<think>",
    '"tool":',
    "思维链",
    "<json>",
    '"ability":',
)

_EXTRACT_SYSTEM = """你是企业知识库入库前的质检助手。请从给定段落提炼可检索的精华知识。
要求：
1. 去掉大段原始测试数据、重复废话，保留规则、流程、接口、结论、关键指标。
2. 输出必须是 JSON 对象，不要 markdown 代码块。
3. 字段：
   - essence: string，精华 Markdown（200~800字为宜）
   - anchor_labels: string[]，1~3 个「模块-功能」风格锚点中文名
   - scope: object，可含 product/version/environment（字符串，可空）
   - doc_hint: string，段落类型提示 prd|performance|general
"""


def is_thinking_chain_paragraph(raw_text: str) -> bool:
    """判断是否为思维链类段落（适合快速通道）。"""
    sample = raw_text[:4000]
    return any(m in sample for m in _THINKING_CHAIN_MARKERS)


async def extract_paragraph_essence(
    raw_text: str,
    *,
    doc_type: str,
    product: str,
    version: str,
    environment: str,
) -> dict[str, Any]:
    """调用 LLM 提炼段落精华；思维链类段落走快速通道。"""
    if is_thinking_chain_paragraph(raw_text):
        return {
            "essence": raw_text[:2000].strip(),
            "anchor_labels": [],
            "scope": {},
            "doc_hint": doc_type,
        }
    user = (
        f"文档类型: {doc_type}\n"
        f"产品: {product or '未指定'}\n"
        f"版本: {version or '未指定'}\n"
        f"环境: {environment or '未指定'}\n\n"
        f"段落原文：\n{raw_text[:8000]}"
    )
    try:
        out = await chat(
            [
                {"role": "system", "content": _EXTRACT_SYSTEM},
                {"role": "user", "content": user},
            ],
            temperature=0.2,
            max_tokens=2048,
            think=False,
        )
        data = extract_json_object(out)
        essence = str(data.get("essence") or "").strip()
        if not essence:
            essence = raw_text[:1200].strip()
        return {
            "essence": essence,
            "anchor_labels": [str(x) for x in (data.get("anchor_labels") or [])][:3],
            "scope": data.get("scope") if isinstance(data.get("scope"), dict) else {},
            "doc_hint": str(data.get("doc_hint") or doc_type),
        }
    except Exception as exc:
        log.warning("段落提炼失败，使用截断原文: %s", exc)
        return {
            "essence": raw_text[:1200].strip(),
            "anchor_labels": [],
            "scope": {},
            "doc_hint": doc_type,
        }
