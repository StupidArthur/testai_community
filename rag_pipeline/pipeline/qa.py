"""
阶段五：质检与去重（纯规则/算法，零 LLM 生成）。

- 杜撰检测：chunk.raw_text 每句须能在原文中找到（允许空白差异）
- 信息覆盖率 ≥ COVERAGE_MIN_RATIO
- 去重：精确 / SimHash≥0.85 / 余弦≥0.92；保留章节路径更深者
"""

from __future__ import annotations

import logging
import math
import re
from typing import Callable

from rag_pipeline.config import (
    COSINE_SIMILARITY_MIN,
    COVERAGE_MIN_RATIO,
    SIMHASH_SIMILARITY_MIN,
)
from rag_pipeline.models.schemas import Chunk, QualityReport
from rag_pipeline.vectorstore.embeddings import EmbedFn, hash_embed_texts

log = logging.getLogger(__name__)

_RE_SENTENCE = re.compile(r"[^。！？.!?\n]+[。！？.!?]?", re.UNICODE)
_RE_MD_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.M)
_RE_NUM_HEADING = re.compile(r"^(?P<num>\d+(?:\.\d+)+)\.?\s*(?P<title>\S.*)?$", re.M)
_RE_LIST_ITEM = re.compile(r"^(\s*[-*+]|\s*\d+\.)\s+(.+)$", re.M)
_RE_TABLE_ROW = re.compile(r"^\s*\|(.+)\|\s*$", re.M)


def _strip_ws(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def sentence_in_source(sentence: str, source: str) -> bool:
    """字符串模糊匹配：允许空白差异，不允许文字差异。"""
    needle = _strip_ws(sentence)
    if not needle:
        return True
    return needle in _strip_ws(source)


def split_sentences(text: str) -> list[str]:
    """按中英文句号等切句。"""
    parts = []
    for m in _RE_SENTENCE.finditer(text or ""):
        s = m.group(0).strip()
        if s:
            parts.append(s)
    return parts


def check_fabrication(chunks: list[Chunk], source_text: str) -> tuple[bool, list[str]]:
    """杜撰检测：任一句子不在原文即为失败。"""
    failures: list[str] = []
    for c in chunks:
        for sent in split_sentences(c.raw_text):
            if not sentence_in_source(sent, source_text):
                failures.append(f"{c.chunk_id}: {sent[:80]}")
    return (len(failures) == 0), failures


def extract_info_units(source_text: str) -> list[str]:
    """从原文提取关键信息单元：标题、表格单元格、列表项。"""
    units: list[str] = []
    for m in _RE_MD_HEADING.finditer(source_text or ""):
        units.append(m.group(2).strip())
    for m in _RE_NUM_HEADING.finditer(source_text or ""):
        units.append(m.group(0).strip())
    for m in _RE_LIST_ITEM.finditer(source_text or ""):
        units.append(m.group(2).strip())
    for m in _RE_TABLE_ROW.finditer(source_text or ""):
        cells = [c.strip() for c in m.group(1).split("|")]
        for cell in cells:
            if cell and not re.fullmatch(r":?-{3,}:?", cell):
                units.append(cell)
    # 去重保序
    seen: set[str] = set()
    out: list[str] = []
    for u in units:
        key = _strip_ws(u)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(u)
    return out


def check_coverage(chunks: list[Chunk], source_text: str) -> tuple[float, bool, dict]:
    """信息丢失检测：关键单元在任一 chunk.raw_text 中的覆盖率。"""
    units = extract_info_units(source_text)
    if not units:
        return 1.0, True, {"total": 0, "hit": 0, "missed": []}
    blob = "\n".join(c.raw_text for c in chunks)
    hit = 0
    missed: list[str] = []
    for u in units:
        if sentence_in_source(u, blob):
            hit += 1
        else:
            missed.append(u)
    ratio = hit / len(units)
    return ratio, ratio >= COVERAGE_MIN_RATIO, {
        "total": len(units),
        "hit": hit,
        "missed": missed[:50],
    }


def _chapter_depth(path: str) -> int:
    if not path or not path.strip():
        return 0
    return path.count(">") + 1


def _simhash_similarity(a: str, b: str) -> float:
    try:
        from simhash import Simhash
    except ImportError:
        # 无 simhash 库时退化为精确/包含近似
        if a == b:
            return 1.0
        return 0.0
    ha = Simhash(a)
    hb = Simhash(b)
    dist = ha.distance(hb)
    # 64-bit SimHash
    return 1.0 - (dist / 64.0)


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _prefer(a: Chunk, b: Chunk) -> Chunk:
    """保留章节路径更深的 chunk；同深保留 index 更小。"""
    da, db = _chapter_depth(a.chapter_path), _chapter_depth(b.chapter_path)
    if da != db:
        return a if da > db else b
    return a if a.chunk_index <= b.chunk_index else b


def dedupe_chunks(
    chunks: list[Chunk],
    *,
    embed_fn: EmbedFn | None = None,
    enable_semantic: bool = True,
) -> tuple[list[Chunk], dict[str, int]]:
    """精确 / 模糊 / 语义去重。"""
    stats = {
        "exact_duplicates_removed": 0,
        "fuzzy_duplicates_removed": 0,
        "semantic_duplicates_removed": 0,
    }
    if not chunks:
        return [], stats

    # 1) 精确去重
    by_raw: dict[str, Chunk] = {}
    for c in chunks:
        key = c.raw_text
        if key in by_raw:
            stats["exact_duplicates_removed"] += 1
            by_raw[key] = _prefer(by_raw[key], c)
        else:
            by_raw[key] = c
    stage1 = sorted(by_raw.values(), key=lambda x: x.chunk_index)

    # 2) SimHash 模糊去重
    kept: list[Chunk] = []
    for c in stage1:
        dup_idx = -1
        for i, k in enumerate(kept):
            if _simhash_similarity(c.raw_text, k.raw_text) >= SIMHASH_SIMILARITY_MIN:
                dup_idx = i
                break
        if dup_idx >= 0:
            stats["fuzzy_duplicates_removed"] += 1
            kept[dup_idx] = _prefer(kept[dup_idx], c)
        else:
            kept.append(c)

    # 3) 语义去重
    if enable_semantic and len(kept) > 1:
        fn: EmbedFn = embed_fn or hash_embed_texts
        try:
            vectors = fn([c.chunk_text for c in kept])
        except Exception as exc:  # noqa: BLE001
            log.warning("semantic dedupe skipped: %s", exc)
            vectors = []
        if vectors and len(vectors) == len(kept):
            drop: set[int] = set()
            for i in range(len(kept)):
                if i in drop:
                    continue
                for j in range(i + 1, len(kept)):
                    if j in drop:
                        continue
                    if _cosine(vectors[i], vectors[j]) >= COSINE_SIMILARITY_MIN:
                        winner = _prefer(kept[i], kept[j])
                        loser_idx = j if winner is kept[i] else i
                        drop.add(loser_idx)
                        stats["semantic_duplicates_removed"] += 1
                        if loser_idx == i:
                            break
            kept = [c for i, c in enumerate(kept) if i not in drop]

    # 重排 index / id / 邻接留给 annotate 之后；此处只重排 index 与 id
    kept = sorted(kept, key=lambda x: x.chunk_index)
    doc_id = kept[0].doc_id if kept else ""
    for i, c in enumerate(kept):
        c.chunk_index = i
        c.chunk_id = f"{doc_id}_{i:04d}"
    for i, c in enumerate(kept):
        c.prev_chunk_id = kept[i - 1].chunk_id if i > 0 else None
        c.next_chunk_id = kept[i + 1].chunk_id if i + 1 < len(kept) else None
        c.doc_summary = c.doc_summary if i == 0 else None
        if i == 0 and kept and kept[0].doc_summary is None:
            # 若原 0 号被删，把摘要挂到新的 0
            pass
    return kept, stats


def quality_check_and_dedupe(
    chunks: list[Chunk],
    *,
    source_text: str,
    embed_fn: EmbedFn | None = None,
    enable_semantic: bool = True,
) -> tuple[list[Chunk], QualityReport]:
    """杜撰检测、覆盖率、去重。"""
    before = len(chunks)
    fab_ok, fab_fail = check_fabrication(chunks, source_text)
    coverage, cov_ok, cov_detail = check_coverage(chunks, source_text)
    deduped, stats = dedupe_chunks(
        chunks, embed_fn=embed_fn, enable_semantic=enable_semantic
    )
    # 去重后复检杜撰（正文未改，应仍通过）
    fab_ok2, fab_fail2 = check_fabrication(deduped, source_text)
    coverage2, cov_ok2, cov_detail2 = check_coverage(deduped, source_text)

    report = QualityReport(
        fabrication_passed=fab_ok and fab_ok2,
        fabrication_failures=(fab_fail or fab_fail2)[:50],
        coverage_ratio=coverage2,
        coverage_passed=cov_ok2,
        exact_duplicates_removed=stats["exact_duplicates_removed"],
        fuzzy_duplicates_removed=stats["fuzzy_duplicates_removed"],
        semantic_duplicates_removed=stats["semantic_duplicates_removed"],
        chunk_count_before=before,
        chunk_count_after=len(deduped),
        details={"coverage_before": cov_detail, "coverage_after": cov_detail2},
    )
    return deduped, report
