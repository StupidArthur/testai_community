"""
阶段二：结构解析与层级保留（纯规则，零 AI）。

- Markdown 标题：^#{1,6}\\s
- 编号伪标题：^\\d+(\\.\\d+)+（如 3.2.复杂过程优化）
- 章节路径：1.概述 > 1.1.诞生
- 表格整块 is_table=True
- 连续 2+ 列表行 is_list_block=True，与前导描述句合并
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

UnitType = Literal["heading", "paragraph", "table", "list_block", "code_block"]

_RE_MD_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
# 编号伪标题：至少两级编号，避免把「1. 普通列表」误判为标题（列表另有规则）
_RE_NUM_HEADING = re.compile(
    r"^(?P<num>\d+(?:\.\d+)+)\.?\s*(?P<title>\S.*)?$"
)
_RE_LIST_ITEM = re.compile(r"^(\s*[-*+]|\s*\d+\.)\s+")
_RE_CN_ENUM = re.compile(
    r"^(首先|其次|再次|然后|接着|最后|还有|另外|其一|其二|其三|其四|"
    r"第一[，,]|第二[，,]|第三[，,]|第四[，,]|第[一二三四五代六七八九十]+[是为：:])"
)
_RE_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$")
_RE_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")


def _is_list_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    if _RE_LIST_ITEM.match(s):
        return True
    return bool(_RE_CN_ENUM.match(s))


@dataclass
class StructuralUnit:
    """结构解析后的语义单元（尚未按字数切分）。"""

    unit_type: UnitType
    text: str
    chapter_path: str
    heading_level: int = 0
    is_table: bool = False
    is_list_block: bool = False
    is_code_block: bool = False
    heading_title: str = ""


@dataclass
class ParseResult:
    """结构解析结果。"""

    units: list[StructuralUnit] = field(default_factory=list)
    doc_title: str = ""
    h1_titles: list[str] = field(default_factory=list)
    h2_titles: list[str] = field(default_factory=list)


def _format_path_segment(num: str, title: str) -> str:
    """生成路径段：优先「编号.标题」。"""
    title = (title or "").strip().strip("#").strip()
    num = num.strip().rstrip(".")
    if not title:
        return num
    # 标题若已含编号前缀则直接用标题
    if title.startswith(num):
        return title.replace(" ", "")
    return f"{num}.{title}".replace(" ", "")


def _md_heading_segment(level: int, title: str) -> str:
    """Markdown 标题路径段。"""
    title = title.strip()
    # 若标题本身以编号开头，规范化空格
    m = _RE_NUM_HEADING.match(title)
    if m:
        return _format_path_segment(m.group("num"), m.group("title") or "")
    return title


def _extract_leading_num(segment: str) -> str | None:
    m = re.match(r"^(\d+(?:\.\d+)*)", (segment or "").strip())
    return m.group(1) if m else None


def _push_numbered_stack(stack: list[str], segment: str, num: str) -> None:
    """按编号前缀保留祖先，避免跨一级章节污染路径。"""
    kept: list[str] = []
    for s in stack:
        n = _extract_leading_num(s)
        if n and num.startswith(n + "."):
            kept.append(s)
    kept.append(segment)
    stack[:] = kept


def _path_from_stack(stack: list[str]) -> str:
    return " > ".join(stack)


def _is_table_block_start(lines: list[str], i: int) -> bool:
    if i + 1 >= len(lines):
        return False
    return bool(_RE_TABLE_ROW.match(lines[i])) and bool(_RE_TABLE_SEP.match(lines[i + 1]))


def _consume_table(lines: list[str], start: int) -> tuple[str, int]:
    buf = [lines[start], lines[start + 1]]
    j = start + 2
    while j < len(lines) and _RE_TABLE_ROW.match(lines[j]):
        buf.append(lines[j])
        j += 1
    return "\n".join(buf), j


def _consume_code_block(lines: list[str], start: int) -> tuple[str, int]:
    fence = lines[start].lstrip()[:3]
    buf = [lines[start]]
    j = start + 1
    while j < len(lines):
        buf.append(lines[j])
        if lines[j].lstrip().startswith(fence):
            j += 1
            break
        j += 1
    return "\n".join(buf), j


def _consume_list_block(lines: list[str], start: int) -> tuple[str, int]:
    """从 start 起消费连续列表行（至少由调用方保证可形成列表）。"""
    buf = [lines[start]]
    j = start + 1
    while j < len(lines):
        if not lines[j].strip():
            # 空行后若仍是列表则继续，否则结束
            if j + 1 < len(lines) and _is_list_line(lines[j + 1]):
                buf.append(lines[j])
                j += 1
                continue
            break
        if _is_list_line(lines[j]):
            buf.append(lines[j])
            j += 1
            continue
        break
    return "\n".join(buf), j


def _count_list_run(lines: list[str], start: int) -> int:
    n = 0
    j = start
    while j < len(lines):
        if not lines[j].strip():
            if j + 1 < len(lines) and _is_list_line(lines[j + 1]):
                j += 1
                continue
            break
        if _is_list_line(lines[j]):
            n += 1
            j += 1
            continue
        break
    return n


def parse_structure(cleaned_text: str, *, fallback_doc_title: str = "") -> ParseResult:
    """
    解析清洗后文本的结构单元与章节路径。

    参数：
        cleaned_text: 阶段一输出
        fallback_doc_title: 无一级标题时的文档标题回退
    """
    text = cleaned_text or ""
    lines = text.split("\n")
    stack: list[str] = []
    units: list[StructuralUnit] = []
    h1: list[str] = []
    h2: list[str] = []
    doc_title = fallback_doc_title.strip()

    i = 0
    pending_lead: str | None = None  # 列表前导描述句

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # 空行：冲刷前导描述为段落
        if not stripped:
            if pending_lead is not None:
                units.append(
                    StructuralUnit(
                        unit_type="paragraph",
                        text=pending_lead,
                        chapter_path=_path_from_stack(stack),
                        heading_level=len(stack),
                    )
                )
                pending_lead = None
            i += 1
            continue

        # 代码块
        if stripped.startswith("```"):
            if pending_lead is not None:
                units.append(
                    StructuralUnit(
                        unit_type="paragraph",
                        text=pending_lead,
                        chapter_path=_path_from_stack(stack),
                        heading_level=len(stack),
                    )
                )
                pending_lead = None
            block, i = _consume_code_block(lines, i)
            units.append(
                StructuralUnit(
                    unit_type="code_block",
                    text=block,
                    chapter_path=_path_from_stack(stack),
                    heading_level=len(stack),
                    is_code_block=True,
                )
            )
            continue

        # 表格
        if _is_table_block_start(lines, i):
            if pending_lead is not None:
                units.append(
                    StructuralUnit(
                        unit_type="paragraph",
                        text=pending_lead,
                        chapter_path=_path_from_stack(stack),
                        heading_level=len(stack),
                    )
                )
                pending_lead = None
            block, i = _consume_table(lines, i)
            units.append(
                StructuralUnit(
                    unit_type="table",
                    text=block,
                    chapter_path=_path_from_stack(stack),
                    heading_level=len(stack),
                    is_table=True,
                )
            )
            continue

        # Markdown 标题
        m_md = _RE_MD_HEADING.match(stripped)
        if m_md:
            if pending_lead is not None:
                units.append(
                    StructuralUnit(
                        unit_type="paragraph",
                        text=pending_lead,
                        chapter_path=_path_from_stack(stack),
                        heading_level=len(stack),
                    )
                )
                pending_lead = None
            level = len(m_md.group(1))
            title = m_md.group(2).strip()
            segment = _md_heading_segment(level, title)
            stack = stack[: level - 1]
            stack.append(segment)
            if level == 1:
                if not doc_title:
                    doc_title = title
                h1.append(title)
            elif level == 2:
                h2.append(title)
            units.append(
                StructuralUnit(
                    unit_type="heading",
                    text=stripped,
                    chapter_path=_path_from_stack(stack),
                    heading_level=level,
                    heading_title=title,
                )
            )
            i += 1
            continue

        # 编号伪标题（至少两级，如 3.2 / 1.1.2）
        m_num = _RE_NUM_HEADING.match(stripped)
        if m_num and not _RE_LIST_ITEM.match(stripped):
            if pending_lead is not None:
                units.append(
                    StructuralUnit(
                        unit_type="paragraph",
                        text=pending_lead,
                        chapter_path=_path_from_stack(stack),
                        heading_level=len(stack),
                    )
                )
                pending_lead = None
            num = m_num.group("num")
            title = (m_num.group("title") or "").strip()
            level = num.count(".") + 1
            segment = _format_path_segment(num, title)
            _push_numbered_stack(stack, segment, num)
            if level == 1:
                h1.append(segment)
            elif level == 2:
                h2.append(segment)
            units.append(
                StructuralUnit(
                    unit_type="heading",
                    text=stripped,
                    chapter_path=_path_from_stack(stack),
                    heading_level=level,
                    heading_title=segment,
                )
            )
            i += 1
            continue

        # 列表块：连续 2+ 行
        list_run = _count_list_run(lines, i)
        if list_run >= 2:
            block, i = _consume_list_block(lines, i)
            if pending_lead is not None:
                block = pending_lead + "\n" + block
                pending_lead = None
            units.append(
                StructuralUnit(
                    unit_type="list_block",
                    text=block,
                    chapter_path=_path_from_stack(stack),
                    heading_level=len(stack),
                    is_list_block=True,
                )
            )
            continue

        # 单行列表：当作普通段落（不足 2 行不成列表块）
        if _is_list_line(stripped) and list_run == 1:
            if pending_lead is not None:
                units.append(
                    StructuralUnit(
                        unit_type="paragraph",
                        text=pending_lead,
                        chapter_path=_path_from_stack(stack),
                        heading_level=len(stack),
                    )
                )
                pending_lead = None
            units.append(
                StructuralUnit(
                    unit_type="paragraph",
                    text=stripped,
                    chapter_path=_path_from_stack(stack),
                    heading_level=len(stack),
                )
            )
            i += 1
            continue

        # 普通段落：若下一非空行为列表块，则作为前导描述
        j = i + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        if j < len(lines) and _count_list_run(lines, j) >= 2:
            pending_lead = stripped if pending_lead is None else pending_lead + "\n" + stripped
            i += 1
            continue

        if pending_lead is not None:
            units.append(
                StructuralUnit(
                    unit_type="paragraph",
                    text=pending_lead,
                    chapter_path=_path_from_stack(stack),
                    heading_level=len(stack),
                )
            )
            pending_lead = None

        units.append(
            StructuralUnit(
                unit_type="paragraph",
                text=stripped,
                chapter_path=_path_from_stack(stack),
                heading_level=len(stack),
            )
        )
        i += 1

    if pending_lead is not None:
        units.append(
            StructuralUnit(
                unit_type="paragraph",
                text=pending_lead,
                chapter_path=_path_from_stack(stack),
                heading_level=len(stack),
            )
        )

    if not doc_title:
        doc_title = fallback_doc_title or "未命名文档"

    return ParseResult(units=units, doc_title=doc_title, h1_titles=h1, h2_titles=h2)
