"""
将长文档按标题 / 列表块 / 表格切分为段落单元。

规则（与知识库入库铁律对齐）：
- 连续列表块（Markdown - / 数字. / 中文枚举词）与前导描述句合并，整体不拆分
- 软上限超出时列表块仍不拆（语义完整优先）
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .config import MAX_PARAGRAPHS_PER_JOB, MIN_PARAGRAPH_CHARS

# 段落软上限（字）；列表块/表格可超限不拆
CHUNK_SOFT_LIMIT = 500

_RE_MD_HEADING = re.compile(r"^(#{1,6})\s+(.+)$")
_RE_NUM_HEADING = re.compile(r"^(?P<num>\d+(?:\.\d+)+)\.?\s*(?P<title>\S.*)?$")
_RE_LIST_MARK = re.compile(r"^(\s*[-*+]|\s*\d+\.)\s+\S")
# Word/docx 常见中文枚举起句（无 - 前缀）
_RE_CN_ENUM = re.compile(
    r"^(首先|其次|再次|然后|接着|最后|还有|另外|其一|其二|其三|其四|"
    r"第一[，,]|第二[，,]|第三[，,]|第四[，,]|第[一二三四五代六七八九十]+[是为：:])"
)
_RE_TABLE_ROW = re.compile(r"^\s*\|.+\|\s*$")
_RE_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$")


@dataclass
class SectionSlice:
    """一个段落切片。"""

    seq: int
    section_path: str
    raw_text: str
    is_table: bool = False
    is_list_block: bool = False


def _is_heading(line: str) -> bool:
    s = line.strip()
    if _RE_MD_HEADING.match(s):
        return True
    if _RE_NUM_HEADING.match(s) and not _RE_LIST_MARK.match(s):
        return True
    return False


def _heading_title(line: str) -> str:
    s = line.strip()
    m = _RE_MD_HEADING.match(s)
    if m:
        return m.group(2).strip()
    m = _RE_NUM_HEADING.match(s)
    if m:
        num = m.group("num")
        title = (m.group("title") or "").strip()
        return f"{num}.{title}".replace(" ", "") if title else num
    return s


def _is_list_item(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    if _RE_LIST_MARK.match(s):
        return True
    if _RE_CN_ENUM.match(s):
        return True
    return False


def _is_table_row(line: str) -> bool:
    return bool(_RE_TABLE_ROW.match(line.strip()))


def _extract_leading_num(segment: str) -> str | None:
    m = re.match(r"^(\d+(?:\.\d+)*)", (segment or "").strip())
    return m.group(1) if m else None


def _path_push(stack: list[str], title: str, level: int, *, num: str | None = None) -> str:
    """
    更新章节路径栈。

    编号标题按编号前缀裁剪祖先（避免 1.1 残留到 6.x）；
    Markdown 标题按 level 裁剪。
    """
    if num:
        kept: list[str] = []
        for s in stack:
            n = _extract_leading_num(s)
            if n and (num.startswith(n + ".") or num == n):
                if num.startswith(n + "."):
                    kept.append(s)
        kept.append(title)
        stack[:] = kept
    else:
        stack[:] = stack[: max(0, level - 1)]
        stack.append(title)
    return " > ".join(stack)


def _heading_level(line: str) -> int:
    s = line.strip()
    m = _RE_MD_HEADING.match(s)
    if m:
        return len(m.group(1))
    m = _RE_NUM_HEADING.match(s)
    if m:
        return m.group("num").count(".") + 1
    return 1


def _consume_table(lines: list[str], start: int) -> tuple[str, int]:
    buf = [lines[start]]
    j = start + 1
    if j < len(lines) and _RE_TABLE_SEP.match(lines[j].strip()):
        buf.append(lines[j])
        j += 1
    while j < len(lines) and _is_table_row(lines[j]):
        buf.append(lines[j])
        j += 1
    return "\n".join(buf).strip(), j


def _count_list_run(lines: list[str], start: int) -> int:
    n = 0
    j = start
    while j < len(lines):
        if not lines[j].strip():
            # 空行后仍是列表则继续
            if j + 1 < len(lines) and _is_list_item(lines[j + 1]):
                j += 1
                continue
            break
        if _is_list_item(lines[j]):
            n += 1
            j += 1
            continue
        break
    return n


def _consume_list_block(lines: list[str], start: int) -> tuple[str, int]:
    buf: list[str] = []
    j = start
    while j < len(lines):
        if not lines[j].strip():
            if j + 1 < len(lines) and _is_list_item(lines[j + 1]):
                buf.append(lines[j])
                j += 1
                continue
            break
        if _is_list_item(lines[j]):
            buf.append(lines[j])
            j += 1
            continue
        break
    return "\n".join(buf).strip(), j


def _split_oversized_plain(text: str, limit: int) -> list[str]:
    """普通段落超限按空行/句号切；不用于列表/表格。"""
    text = text.strip()
    if len(text) <= limit:
        return [text] if text else []
    parts: list[str] = []
    remaining = text
    while len(remaining) > limit:
        window = remaining[:limit]
        cut = -1
        for sep in ("\n\n", "\n", "。", "！", "？"):
            idx = window.rfind(sep)
            if idx >= max(20, limit // 5):
                cut = idx + len(sep)
                break
        if cut <= 0:
            cut = limit
        piece = remaining[:cut].strip()
        if piece:
            parts.append(piece)
        remaining = remaining[cut:].strip()
    if remaining:
        parts.append(remaining)
    return parts


def split_plain_text_to_sections(text: str) -> list[SectionSlice]:
    """
    结构感知切分：标题边界、列表块+前导句、表格整块。
    """
    text = (text or "").strip()
    if not text:
        return []

    # 保留空行信息：按单行扫描
    lines = text.split("\n")
    stack: list[str] = []
    units: list[dict] = []
    pending_lead: str | None = None
    i = 0

    def flush_lead() -> None:
        nonlocal pending_lead
        if pending_lead:
            units.append(
                {
                    "raw_text": pending_lead,
                    "section_path": " > ".join(stack) or "正文",
                    "is_table": False,
                    "is_list_block": False,
                }
            )
            pending_lead = None

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        # 表格
        if _is_table_row(stripped) and (
            i + 1 < len(lines) and _RE_TABLE_SEP.match(lines[i + 1].strip())
            or (i + 1 < len(lines) and _is_table_row(lines[i + 1]))
        ):
            flush_lead()
            block, i = _consume_table(lines, i)
            units.append(
                {
                    "raw_text": block,
                    "section_path": " > ".join(stack) or "正文",
                    "is_table": True,
                    "is_list_block": False,
                }
            )
            continue

        # 标题：结束当前块
        if _is_heading(stripped):
            flush_lead()
            title = _heading_title(stripped)
            level = _heading_level(stripped)
            num_m = _RE_NUM_HEADING.match(stripped)
            num = num_m.group("num") if num_m and not _RE_MD_HEADING.match(stripped) else None
            path = _path_push(stack, title, level, num=num)
            # 标题暂存，与后续首段/列表/表绑定
            units.append(
                {
                    "raw_text": stripped,
                    "section_path": path,
                    "is_table": False,
                    "is_list_block": False,
                    "is_heading": True,
                    "heading_level": level,
                }
            )
            i += 1
            continue

        # 列表块：≥2 行
        run = _count_list_run(lines, i)
        if run >= 2:
            block, i = _consume_list_block(lines, i)
            if pending_lead:
                block = pending_lead + "\n\n" + block
                pending_lead = None
            # 若上一 unit 是标题，绑到标题
            if units and units[-1].get("is_heading"):
                h = units.pop()
                block = h["raw_text"] + "\n\n" + block
                path = h["section_path"]
            else:
                path = " > ".join(stack) or "正文"
            units.append(
                {
                    "raw_text": block,
                    "section_path": path,
                    "is_table": False,
                    "is_list_block": True,
                }
            )
            continue

        # 单行列表：当作普通段
        # 普通段落：若下一非空是列表块，则作前导
        j = i + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        if j < len(lines) and _count_list_run(lines, j) >= 2:
            pending_lead = stripped if pending_lead is None else pending_lead + "\n\n" + stripped
            i += 1
            continue

        flush_lead()
        # 绑标题
        if units and units[-1].get("is_heading"):
            h = units.pop()
            merged = h["raw_text"] + "\n\n" + stripped
            for piece in _split_oversized_plain(merged, CHUNK_SOFT_LIMIT):
                units.append(
                    {
                        "raw_text": piece,
                        "section_path": h["section_path"],
                        "is_table": False,
                        "is_list_block": False,
                    }
                )
            i += 1
            continue

        for piece in _split_oversized_plain(stripped, CHUNK_SOFT_LIMIT):
            units.append(
                {
                    "raw_text": piece,
                    "section_path": " > ".join(stack) or "正文",
                    "is_table": False,
                    "is_list_block": False,
                }
            )
        i += 1

    flush_lead()
    # 残留孤立标题
    for u in units:
        u.pop("is_heading", None)
        u.pop("heading_level", None)

    slices: list[SectionSlice] = []
    seq = 0
    for u in units:
        raw = (u.get("raw_text") or "").strip()
        if not raw:
            continue
        is_atomic = bool(u.get("is_list_block") or u.get("is_table"))
        # 标题绑定块以标题行开头（# 或编号）——同样视为结构块，不做过短丢弃
        looks_headed = _is_heading(raw.split("\n", 1)[0].strip())
        if not is_atomic and not looks_headed and len(raw) < MIN_PARAGRAPH_CHARS:
            if slices and slices[-1].section_path == u["section_path"] and not slices[-1].is_list_block and not slices[-1].is_table:
                slices[-1].raw_text = slices[-1].raw_text + "\n\n" + raw
                continue
            if len(raw) < max(40, MIN_PARAGRAPH_CHARS // 3):
                continue
        slices.append(
            SectionSlice(
                seq=seq,
                section_path=str(u["section_path"]),
                raw_text=raw,
                is_table=bool(u.get("is_table")),
                is_list_block=bool(u.get("is_list_block")),
            )
        )
        seq += 1
        if seq >= MAX_PARAGRAPHS_PER_JOB:
            break

    # 有结构单元却被滤光时：保留全部结构块（禁止退回「全文粘贴」以免跨章）
    if not slices and units:
        for u in units:
            raw = (u.get("raw_text") or "").strip()
            if not raw:
                continue
            slices.append(
                SectionSlice(
                    seq=len(slices),
                    section_path=str(u.get("section_path") or "正文"),
                    raw_text=raw,
                    is_table=bool(u.get("is_table")),
                    is_list_block=bool(u.get("is_list_block")),
                )
            )
    elif not slices and text.strip():
        slices.append(SectionSlice(seq=0, section_path="全文", raw_text=text[:12000]))
    # 重编号
    for i, s in enumerate(slices):
        s.seq = i
    return slices
