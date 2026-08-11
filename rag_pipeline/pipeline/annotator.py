"""
阶段四：元数据标注（纯规则，零 AI）。

- 文档摘要：标题 + 一/二级标题拼接（文档级一次）
- 关键实体：标题文字、大写缩写、位号、标题专有名词
- 邻接：prev_chunk_id / next_chunk_id
"""

from __future__ import annotations

import re

from rag_pipeline.models.schemas import Chunk
from rag_pipeline.pipeline.parser import ParseResult

_RE_ACRONYM = re.compile(r"\b[A-Z]{2,}\b")
_RE_TAG_NO = re.compile(r"\b\d+-[A-Z]+-\d+\b")
# 标题中的中文专有名词片段（2~12 字连续汉字/字母数字）
_RE_TITLE_TERM = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]{2,12}")


def build_doc_summary(parse_result: ParseResult) -> str:
    """生成文档级摘要（仅规则拼接，不调用 LLM）。"""
    title = parse_result.doc_title.strip() or "未命名文档"
    chapters: list[str] = []
    seen: set[str] = set()
    for t in parse_result.h1_titles + parse_result.h2_titles:
        key = t.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        chapters.append(key)
    if chapters:
        return f"{title}。章节：{' '.join(chapters)}"
    return f"{title}。"


def extract_key_entities(chunk: Chunk, *, heading_titles: list[str]) -> list[str]:
    """从 chunk 正文与标题集合中规则抽取关键实体。"""
    ents: list[str] = []
    seen: set[str] = set()

    def add(x: str) -> None:
        x = x.strip()
        if not x or x in seen:
            return
        seen.add(x)
        ents.append(x)

    for t in heading_titles:
        add(t)
        for m in _RE_TITLE_TERM.findall(t):
            if len(m) >= 2:
                add(m)

    text = chunk.raw_text
    for m in _RE_ACRONYM.findall(text):
        add(m)
    for m in _RE_TAG_NO.findall(text):
        add(m)

    # 当前章节路径段也作为实体
    if chunk.chapter_path:
        for seg in chunk.chapter_path.split(">"):
            add(seg.strip())

    return ents


def annotate_chunks(
    chunks: list[Chunk],
    *,
    parse_result: ParseResult,
) -> tuple[list[Chunk], str]:
    """
    为 chunks 标注摘要、实体、邻接关系。

    返回：(标注后的 chunks, doc_summary)
    """
    doc_summary = build_doc_summary(parse_result)
    heading_titles = list(parse_result.h1_titles) + list(parse_result.h2_titles)
    for u in parse_result.units:
        if u.heading_title:
            heading_titles.append(u.heading_title)

    n = len(chunks)
    for i, c in enumerate(chunks):
        c.key_entities = extract_key_entities(c, heading_titles=heading_titles)
        c.prev_chunk_id = chunks[i - 1].chunk_id if i > 0 else None
        c.next_chunk_id = chunks[i + 1].chunk_id if i + 1 < n else None
        # 仅 chunk_index=0 携带文档摘要
        c.doc_summary = doc_summary if c.chunk_index == 0 else None

    return chunks, doc_summary
