"""Bug4：top_k 默认增大；标题必须绑正文，不得标题独块（有后续时）。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.ai_service.document.loaders import load_document_text_and_images
from app.data_cleaning.noise import clean_noise
from app.data_cleaning.splitter import split_plain_text_to_sections
from app.platform.config import KB_RAG_TOP_K


_SIX = ("模拟", "控制", "优化", "预测", "评估", "统计")


def test_bug4_top_k_default_at_least_10() -> None:
    assert KB_RAG_TOP_K >= 10


def test_bug4_heading_binds_following_paragraph() -> None:
    sample = """4.1.模拟

模拟能力用于对装置进行机理或数据驱动仿真。

4.2.控制

控制能力用于闭环调节关键回路。
"""
    slices = split_plain_text_to_sections(sample)
    # 不应出现「仅有标题一行」的独立块（存在后续正文时）
    for s in slices:
        lines = [ln for ln in s.raw_text.splitlines() if ln.strip()]
        if len(lines) == 1 and lines[0].startswith("4."):
            raise AssertionError(f"标题未绑定正文: {s.raw_text}")
    sim = [s for s in slices if "4.1" in s.raw_text or "模拟能力" in s.raw_text]
    assert sim and "仿真" in sim[0].raw_text


def test_bug4_six_scopes_have_body_chunks() -> None:
    """六大能力各自应有含描述正文的 chunk（非仅标题）。"""
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
    plain = clean_noise(load_document_text_and_images(path)[0] or "")
    # 文档中应出现六大能力总述
    assert all(x in plain for x in _SIX) or "Scopes" in plain
    slices = split_plain_text_to_sections(plain)
    # 4.1~4.6 小节：标题+正文同块
    found = 0
    for prefix, keyword in (
        ("4.1", "模拟"),
        ("4.2", "控制"),
        ("4.3", "优化"),
        ("4.4", "预测"),
        ("4.5", "评估"),
        ("4.6", "统计"),
    ):
        hits = [s for s in slices if prefix in s.raw_text or prefix in s.section_path]
        if not hits:
            # 宽松：关键词在某块且块长度明显大于标题
            hits = [s for s in slices if keyword in s.raw_text and len(s.raw_text) > 30]
        assert hits, f"缺少 {prefix}/{keyword} chunk"
        assert len(hits[0].raw_text) > 20, f"{prefix} 不应只有空标题"
        found += 1
    assert found == 6
