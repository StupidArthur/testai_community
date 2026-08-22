"""
阶段三：语义单元切分（纯算法，零 AI）。

原则：
- 表格 / 列表块 / 代码块不可分割（可超软上限）
- 标题与下方第一个段落 / 列表 / 表格绑定，标题不单独成块（若有后续内容）
- 软上限 CHUNK_SOFT_LIMIT，普通段落超过时在段落边界切分
- raw_text：纯原文；chunk_text：[章节路径]\\n + 原文
"""

from __future__ import annotations

from rag_pipeline.config import CHUNK_SOFT_LIMIT
from rag_pipeline.models.schemas import Chunk, utc_now_iso
from rag_pipeline.pipeline.parser import StructuralUnit


def _make_chunk_text(chapter_path: str, raw_text: str) -> str:
    path = (chapter_path or "").strip()
    body = raw_text.strip()
    if path:
        return f"[{path}]\n{body}"
    return body


def _split_oversized_paragraph(text: str, limit: int) -> list[str]:
    """普通段落超限切分；列表/表格/并列层级块不得调用本函数拆开。"""
    text = text.strip()
    if not text:
        return []
    # 并列「xx层」描述整段保留
    layer_hits = sum(
        1
        for line in text.split("\n")
        if (s := line.strip()) and len(s) <= 40 and s.endswith("层")
    )
    if layer_hits >= 3:
        return [text]
    if len(text) <= limit:
        return [text]

    parts: list[str] = []
    remaining = text
    while len(remaining) > limit:
        window = remaining[:limit]
        cut = -1
        for sep in ("\n\n", "\n", "。", "！", "？", ".", ";", "；"):
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


def _append_piece(
    raw_pieces: list[dict],
    *,
    raw_text: str,
    chapter_path: str,
    heading_level: int,
    is_table: bool,
    is_list_block: bool,
) -> None:
    raw = raw_text.strip()
    if not raw:
        return
    raw_pieces.append(
        {
            "raw_text": raw,
            "chapter_path": chapter_path,
            "heading_level": heading_level,
            "is_table": is_table,
            "is_list_block": is_list_block,
        }
    )


def split_to_chunks(
    units: list[StructuralUnit],
    *,
    doc_id: str,
    doc_title: str,
    soft_limit: int = CHUNK_SOFT_LIMIT,
) -> list[Chunk]:
    """将结构单元切分为 Chunk 列表（尚未标注实体/邻接）。"""
    raw_pieces: list[dict] = []
    i = 0
    while i < len(units):
        u = units[i]

        if u.unit_type == "heading":
            # 标题与下方第一个段落 / 列表 / 表格绑定
            if i + 1 < len(units):
                nxt = units[i + 1]
                if nxt.unit_type in ("paragraph", "list_block", "table", "code_block") or nxt.is_list_block or nxt.is_table:
                    merged = f"{u.text}\n{nxt.text}".strip()
                    # 列表/表/代码：整块保留，可超 soft_limit
                    if nxt.is_list_block or nxt.is_table or nxt.is_code_block or nxt.unit_type in ("list_block", "table", "code_block"):
                        _append_piece(
                            raw_pieces,
                            raw_text=merged,
                            chapter_path=nxt.chapter_path or u.chapter_path,
                            heading_level=u.heading_level,
                            is_table=nxt.is_table,
                            is_list_block=nxt.is_list_block,
                        )
                    else:
                        for piece in _split_oversized_paragraph(merged, soft_limit):
                            _append_piece(
                                raw_pieces,
                                raw_text=piece,
                                chapter_path=nxt.chapter_path or u.chapter_path,
                                heading_level=u.heading_level,
                                is_table=False,
                                is_list_block=False,
                            )
                    i += 2
                    continue
            # 无后续内容：标题单独成块（不可避免）
            _append_piece(
                raw_pieces,
                raw_text=u.text,
                chapter_path=u.chapter_path,
                heading_level=u.heading_level,
                is_table=False,
                is_list_block=False,
            )
            i += 1
            continue

        if u.is_table or u.is_list_block or u.is_code_block:
            # 不可拆分，允许超过 soft_limit
            _append_piece(
                raw_pieces,
                raw_text=u.text,
                chapter_path=u.chapter_path,
                heading_level=u.heading_level,
                is_table=u.is_table,
                is_list_block=u.is_list_block,
            )
            i += 1
            continue

        for piece in _split_oversized_paragraph(u.text, soft_limit):
            _append_piece(
                raw_pieces,
                raw_text=piece,
                chapter_path=u.chapter_path,
                heading_level=u.heading_level,
                is_table=False,
                is_list_block=False,
            )
        i += 1

    chunks: list[Chunk] = []
    created = utc_now_iso()
    for idx, p in enumerate(raw_pieces):
        raw = p["raw_text"]
        chunk_id = f"{doc_id}_{idx:04d}"
        chunks.append(
            Chunk(
                chunk_id=chunk_id,
                doc_id=doc_id,
                doc_title=doc_title,
                raw_text=raw,
                chunk_text=_make_chunk_text(p["chapter_path"], raw),
                chapter_path=p["chapter_path"],
                heading_level=int(p["heading_level"]),
                chunk_index=idx,
                is_table=bool(p["is_table"]),
                is_list_block=bool(p["is_list_block"]),
                created_at=created,
            )
        )
    for idx, c in enumerate(chunks):
        c.chunk_index = idx
        c.chunk_id = f"{doc_id}_{idx:04d}"
    return chunks
