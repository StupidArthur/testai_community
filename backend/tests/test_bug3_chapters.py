"""Bug3：不同章节内容不得并入同一 chunk。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.ai_service.document.loaders import load_document_text_and_images
from app.data_cleaning.noise import clean_noise
from app.data_cleaning.splitter import split_plain_text_to_sections


def test_bug3_chapter_boundary_not_merged() -> None:
    sample = """6.3.我的对话

进入“我的对话”功能板块后，右边是提问交互框。

根据对话结果，TPT 2 会判断是否需要生成 Agent。

用户可点击保存为 Agent。

6.6.我的模型

进入“我的模型”功能板块后，右边是已经创建的模型。

点击 GET STARTED 开始。
"""
    slices = split_plain_text_to_sections(sample)
    for s in slices:
        has_dialog = "保存为 Agent" in s.raw_text or "我的对话" in s.raw_text and "生成 Agent" in s.raw_text
        has_model = "GET STARTED" in s.raw_text or ("我的模型" in s.raw_text and "已经创建的模型" in s.raw_text)
        assert not (has_dialog and has_model), f"跨章合并: {s.section_path} / {s.raw_text[:80]}"
    # 路径不应残留 1.x 到 6.x
    for s in slices:
        if "6.6" in s.section_path or "我的模型" in s.section_path:
            assert "1.1" not in s.section_path and "诞生" not in s.section_path


def test_bug3_real_tpt2_no_cross_chapter() -> None:
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
    slices = split_plain_text_to_sections(plain)
    mixed = [
        s
        for s in slices
        if ("保存为 Agent" in s.raw_text or "保存为Agent" in s.raw_text)
        and ("GET STARTED" in s.raw_text)
    ]
    assert not mixed, "6.3 与 6.6 内容不应同 chunk"
