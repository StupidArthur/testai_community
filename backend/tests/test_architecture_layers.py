"""六层功能架构应整节保留，不因 500 字软上限被硬切。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.ai_service.document.loaders import load_document_text_and_images
from app.data_cleaning.noise import clean_noise
from app.data_cleaning.splitter import split_plain_text_to_sections

_SIX_LAYERS = (
    "智能交互与知识沉淀层",
    "数据感知与融合层",
    "AI 驱动的装置建模层",
    "智能建模与分析层",
    "智能决策与优化层",
    "闭环执行与集成层",
)


def test_six_architecture_layers_stay_in_one_chunk() -> None:
    sample = """2.1.功能架构

TPT 2 的整体架构设计为一个分层、模块化的平台。

智能交互与知识沉淀层

智能交互与知识沉淀层为用户提供人机交互界面。

数据感知与融合层

数据感知与融合层负责获取异构数据。

AI 驱动的装置建模层

AI 驱动的装置建模层构建装置数字孪生。

智能建模与分析层

智能建模与分析层进行深度分析和建模。

智能决策与优化层

智能决策与优化层生成最优生产运营策略。

闭环执行与集成层

闭环执行与集成层与 DCS 集成实现闭环控制。
"""
    slices = split_plain_text_to_sections(sample)
    hits = [s for s in slices if all(x in s.raw_text for x in _SIX_LAYERS)]
    assert hits, f"六层应在同一 chunk；实际={[ (s.seq, len(s.raw_text)) for s in slices ]}"


def test_six_layers_on_real_tpt2_if_present() -> None:
    db = Path(__file__).resolve().parents[1] / "database_dev.sqlite"
    if not db.is_file():
        return
    conn = sqlite3.connect(str(db))
    row = conn.execute(
        "select original_path from dc_clean_jobs where filename like ? order by created_at desc limit 1",
        ("%TPT%",),
    ).fetchone()
    conn.close()
    if not row:
        return
    path = Path(row[0])
    if not path.is_file():
        return
    plain = clean_noise(load_document_text_and_images(path)[0] or "")
    if "2.1.功能架构" not in plain:
        return
    slices = split_plain_text_to_sections(plain)
    hits = [s for s in slices if all(x in s.raw_text for x in _SIX_LAYERS)]
    assert hits, "TPT2 2.1 六层架构应落在同一 chunk，不得被字数硬切拆散"
