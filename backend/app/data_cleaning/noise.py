"""
确定性噪音清洗（纯正则，零 AI）。

只删除噪音标记，不改写正文文字。
清洗前保护 Markdown / 简易表格，避免空行压缩破坏表结构。
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

_TABLE_PLACEHOLDER = "<<<KB_TABLE_{idx}>>>"


def _is_md_table_row(line: str) -> bool:
    s = line.strip()
    return s.startswith("|") and s.endswith("|") and s.count("|") >= 2


def _is_md_table_sep(line: str) -> bool:
    s = line.strip()
    return bool(re.match(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$", s))


def _extract_tables(text: str) -> tuple[str, list[str]]:
    """抽出 Markdown 表格为占位符，避免后续规则破坏。"""
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
    """删除图片/格式残留/裸链等噪音，保留正文与表格。"""
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
