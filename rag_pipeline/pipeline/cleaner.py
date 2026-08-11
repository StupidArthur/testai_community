"""
阶段一：确定性噪音清洗（纯正则，零 AI）。

铁律：只删除噪音字符/标记，不改写任何正文文字。
清洗前保护 Markdown 表格，清洗后再还原。
"""

from __future__ import annotations

import re

_RE_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)(?:\{[^}]*\})?")
_RE_UNDERLINE = re.compile(r"\[([^\]]*)\]\{\.underline\}")
_RE_SIZE_ATTR = re.compile(r'\{width="[^"]*"\s*height="[^"]*"\}')
_RE_LINK_WITH_TEXT = re.compile(r"\[([^\]]+)\]\(https?[^)]*\)")
_RE_LINK_BARE = re.compile(r"\[\]\(https?[^)]*\)")
_RE_BLANK_LINES = re.compile(r"\n{3,}")
_RE_INVISIBLE = re.compile(r"[\u200B\uFEFF\u0000-\u0008\u000B\u000C]")

_TABLE_PLACEHOLDER = "<<<RAG_TABLE_{idx}>>>"


def _is_md_table_row(line: str) -> bool:
    s = line.strip()
    return s.startswith("|") and s.endswith("|") and s.count("|") >= 2


def _is_md_table_sep(line: str) -> bool:
    s = line.strip()
    return bool(re.match(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$", s))


def _extract_tables(text: str) -> tuple[str, list[str]]:
    lines = text.split("\n")
    out: list[str] = []
    tables: list[str] = []
    i = 0
    while i < len(lines):
        if _is_md_table_row(lines[i]) and i + 1 < len(lines) and (
            _is_md_table_sep(lines[i + 1]) or _is_md_table_row(lines[i + 1])
        ):
            buf = [lines[i]]
            j = i + 1
            while j < len(lines) and (_is_md_table_row(lines[j]) or _is_md_table_sep(lines[j])):
                buf.append(lines[j])
                j += 1
            idx = len(tables)
            tables.append("\n".join(buf))
            out.append(_TABLE_PLACEHOLDER.format(idx=idx))
            i = j
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out), tables


def _restore_tables(text: str, tables: list[str]) -> str:
    for idx, table in enumerate(tables):
        text = text.replace(_TABLE_PLACEHOLDER.format(idx=idx), table)
    return text


def clean_noise(text: str) -> str:
    """删除噪音，不修改任何正文文字；表格整块保护。"""
    if not text:
        return ""
    text, tables = _extract_tables(text)
    text = _RE_IMAGE.sub("", text)
    text = _RE_UNDERLINE.sub(r"\1", text)
    text = _RE_SIZE_ATTR.sub("", text)
    text = _RE_LINK_WITH_TEXT.sub(r"\1", text)
    text = _RE_LINK_BARE.sub("", text)
    text = _RE_BLANK_LINES.sub("\n\n", text)
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = _RE_INVISIBLE.sub("", text)
    text = _restore_tables(text, tables)
    return text.strip()


def main() -> None:
    """本地冒烟。"""
    from pathlib import Path

    from rag_pipeline.pipeline.converter import convert_document_to_raw_text

    sample = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "sample.md"
    raw = convert_document_to_raw_text(sample)
    cleaned = clean_noise(raw)
    print(f"[cleaner] raw={len(raw)} cleaned={len(cleaned)}")
    print(cleaned)


if __name__ == "__main__":
    main()
