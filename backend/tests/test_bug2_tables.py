"""Bug2：对比表在清洗后保留，且整表在同一 chunk。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.ai_service.document.loaders import load_document_text_and_images
from app.data_cleaning.noise import clean_noise
from app.data_cleaning.splitter import split_plain_text_to_sections


def test_bug2_markdown_table_preserved_and_unsplit() -> None:
    sample = """## 1.3 变革

对比如下：

| 维度 | TPT 1 | TPT 2 |
| --- | --- | --- |
| 核心架构 | 传统 Transformer 架构 | MoE 架构（稀疏专家网络） |
| 算力需求 | 算力要求高 | 算力要求大幅度降低 |
| 闭环执行 | 仅提供优化建议 | 运行态闭环控制 |

结语。
"""
    cleaned = clean_noise(sample)
    assert "MoE 架构" in cleaned
    assert "| --- |" in cleaned or "|---|" in cleaned.replace(" ", "")
    slices = split_plain_text_to_sections(cleaned)
    hits = [s for s in slices if "MoE 架构" in s.raw_text and "闭环执行" in s.raw_text]
    assert hits, "整张对比表应在同一 chunk"
    assert hits[0].is_table is True


def test_bug2_real_tpt2_docx_table() -> None:
    db = Path(__file__).resolve().parents[1] / "database_dev.sqlite"
    if not db.is_file():
        return
    conn = sqlite3.connect(str(db))
    row = conn.execute(
        "select original_path from dc_clean_jobs where filename like ? limit 1",
        ("%TPT%",),
    ).fetchone()
    conn.close()
    if not row:
        return
    path = Path(row[0])
    if not path.is_file():
        return
    text, _, _ = load_document_text_and_images(path)
    plain = clean_noise(text or "")
    assert "MoE" in plain, "清洗后应仍含 MoE"
    assert "闭环执行" in plain
    # 标准 markdown 表或至少整块同 chunk
    slices = split_plain_text_to_sections(plain)
    hits = [s for s in slices if "MoE" in s.raw_text and "闭环执行" in s.raw_text]
    assert hits, "MoE 与闭环执行应在同一 chunk"
    # 新 loader 应产出 markdown 表
    assert "|" in hits[0].raw_text
