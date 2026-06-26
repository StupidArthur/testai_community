"""
将长文档按 Markdown 标题切分为段落单元。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .config import MAX_PARAGRAPHS_PER_JOB, MIN_PARAGRAPH_CHARS


@dataclass
class SectionSlice:
    """一个段落切片。"""

    seq: int
    section_path: str
    raw_text: str


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


def _merge_short_blocks(blocks: list[str], min_chars: int) -> list[str]:
    """
    合并连续短块。

    Word/docx 常逐段排版（段间空行），每段往往不足 min_chars；
    不合并会导致整篇文档被 MIN_PARAGRAPH_CHARS 全部过滤。
    """
    if not blocks:
        return []

    merged: list[str] = []
    buf: list[str] = []
    buf_len = 0

    def flush_buf() -> None:
        nonlocal buf, buf_len
        if not buf:
            return
        merged.append("\n\n".join(buf))
        buf = []
        buf_len = 0

    for block in blocks:
        buf.append(block)
        buf_len += len(block) + 2
        if buf_len >= min_chars:
            flush_buf()

    if buf:
        remainder = "\n\n".join(buf)
        if not merged:
            merged.append(remainder)
        elif len(remainder) < min_chars:
            merged[-1] = merged[-1] + "\n\n" + remainder
        else:
            merged.append(remainder)
    return merged


def split_plain_text_to_sections(text: str) -> list[SectionSlice]:
    """
    按 Markdown 标题切分；无标题时按空行分段；过长段再按字数切。
    """
    text = (text or "").strip()
    if not text:
        return []

    sections: list[tuple[str, str]] = []
    matches = list(_HEADING_RE.finditer(text))
    if not matches:
        blocks = [b.strip() for b in re.split(r"\n{2,}", text) if b.strip()]
        merged = _merge_short_blocks(blocks, MIN_PARAGRAPH_CHARS)
        for idx, block in enumerate(merged):
            sections.append((f"段落 {idx + 1}", block))
    else:
        for i, match in enumerate(matches):
            level = len(match.group(1))
            title = match.group(2).strip()
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[start:end].strip()
            content = f"{'#' * level} {title}\n\n{body}".strip() if body else f"{'#' * level} {title}"
            sections.append((title, content))

    slices: list[SectionSlice] = []
    seq = 0
    for path, raw in sections:
        if len(raw) < MIN_PARAGRAPH_CHARS:
            continue
        for part in _maybe_split_long(raw, path):
            if len(part) < MIN_PARAGRAPH_CHARS:
                continue
            slices.append(SectionSlice(seq=seq, section_path=path, raw_text=part))
            seq += 1
            if seq >= MAX_PARAGRAPHS_PER_JOB:
                return slices

    if not slices and text:
        slices.append(SectionSlice(seq=0, section_path="全文", raw_text=text[:12000]))
    return slices


def _maybe_split_long(raw: str, path: str, max_len: int = 6000) -> list[str]:
    if len(raw) <= max_len:
        return [raw]
    parts: list[str] = []
    start = 0
    idx = 1
    while start < len(raw):
        chunk = raw[start : start + max_len]
        parts.append(chunk)
        start += max_len
        idx += 1
    return parts
