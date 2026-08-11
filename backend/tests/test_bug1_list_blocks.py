"""Bug1：连续列表（含中文枚举）与前导句合并验证。"""

from __future__ import annotations

from pathlib import Path

from app.ai_service.document.loaders import load_document_text_and_images
from app.data_cleaning.noise import clean_noise
from app.data_cleaning.splitter import split_plain_text_to_sections

_DIMS = ("逻辑一致性", "机理验证", "历史数据", "约束条件")


def test_bug1_list_block_keeps_four_dimensions_together() -> None:
    """3.5 节四个检查维度必须在同一 chunk。"""
    sample = """3.5.自主推理与验证机制

为了确保输出方案的可靠性，TPT 2 软件实现了独特的自主推理和验证机制。

这一机制类似于人类专家在给出方案前进行反复推敲和验证的过程。软件会对生成的初步方案进行多维度检查：

首先是逻辑一致性检查，确保方案内部没有矛盾，步骤之间符合逻辑顺序；

其次是机理验证，利用内置的物理化学模型或仿真工具，模拟方案实施后的效果；

再次是历史数据验证，将方案与历史案例进行比对；

最后是约束条件检查，确保方案在实际实施中满足安全、环保、设备能力等约束。

这种自主反思和迭代优化的机制，使 TPT 2 软件能够不断完善。
"""
    slices = split_plain_text_to_sections(sample)
    hits = [s for s in slices if all(d in s.raw_text for d in _DIMS)]
    assert hits, f"四个维度应在同一段内；实际段数={len(slices)} " + str(
        [(s.seq, s.raw_text[:60]) for s in slices]
    )
    assert hits[0].is_list_block or all(d in hits[0].raw_text for d in _DIMS)


def test_bug1_markdown_dash_list_with_lead() -> None:
    """Markdown - 列表与前导句合并。"""
    sample = """## 检查维度

系统进行下列检查：

- 逻辑一致性检查
- 机理验证
- 历史数据验证
- 约束条件检查

后续说明。
"""
    slices = split_plain_text_to_sections(sample)
    hits = [s for s in slices if all(d in s.raw_text for d in _DIMS)]
    assert len(hits) >= 1
    assert "系统进行下列检查" in hits[0].raw_text


def test_bug1_on_real_tpt2_docx_if_present() -> None:
    """若开发库仍有 TPT2 原件，对全文切分做同样断言。"""
    import sqlite3

    db = Path(__file__).resolve().parents[1] / "database_dev.sqlite"
    if not db.is_file():
        return
    conn = sqlite3.connect(str(db))
    row = conn.execute(
        "select original_path from dc_clean_jobs where filename like '%TPT%' order by created_at desc limit 1"
    ).fetchone()
    conn.close()
    if not row:
        return
    path = Path(row[0])
    if not path.is_file():
        return
    text, _, _ = load_document_text_and_images(path)
    plain = clean_noise(text or "")
    slices = split_plain_text_to_sections(plain)
    hits = [s for s in slices if all(d in s.raw_text for d in _DIMS)]
    assert hits, "TPT2 文档 3.5 四维度应在同一 chunk"
