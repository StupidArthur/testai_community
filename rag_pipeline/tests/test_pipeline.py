"""
Pipeline 全流程单元测试（零 LLM 入库路径）。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from rag_pipeline.pipeline.cleaner import clean_noise
from rag_pipeline.pipeline.converter import (
    ConverterError,
    SUPPORTED_EXTENSIONS,
    convert_document_to_raw_text,
    convert_md_to_text,
)
from rag_pipeline.pipeline.parser import parse_structure
from rag_pipeline.pipeline.pipeline import run_pipeline
from rag_pipeline.pipeline.qa import (
    check_coverage,
    check_fabrication,
    quality_check_and_dedupe,
)
from rag_pipeline.qa.generator import (
    ANSWER_UNAVAILABLE,
    generate_answer,
    validate_answer_entities,
)
from rag_pipeline.vectorstore.embeddings import hash_embed_texts
from rag_pipeline.vectorstore.store import reset_store_cache

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SAMPLE_MD = FIXTURES / "sample.md"


@pytest.fixture()
def chroma_dir(tmp_path: Path):
    reset_store_cache()
    d = tmp_path / "chroma"
    d.mkdir()
    yield d
    reset_store_cache()


def test_supported_extensions_include_docx_pdf_md() -> None:
    assert ".docx" in SUPPORTED_EXTENSIONS
    assert ".pdf" in SUPPORTED_EXTENSIONS
    assert ".md" in SUPPORTED_EXTENSIONS


def test_convert_md_preserves_body_text() -> None:
    raw = convert_md_to_text(SAMPLE_MD)
    assert "TPT 是流程工业时序大模型产品。" in raw


def test_convert_document_to_raw_text_md() -> None:
    raw = convert_document_to_raw_text(SAMPLE_MD)
    assert "产品面向流程工业时序场景。" in raw


def test_convert_missing_file_raises() -> None:
    with pytest.raises(ConverterError, match="文件不存在"):
        convert_document_to_raw_text(FIXTURES / "not_exists.md")


def test_convert_unsupported_extension_raises() -> None:
    tmp = FIXTURES / "sample.txt"
    tmp.write_text("hello", encoding="utf-8")
    try:
        with pytest.raises(ConverterError, match="不支持的文件类型"):
            convert_document_to_raw_text(tmp)
    finally:
        tmp.unlink(missing_ok=True)


def test_clean_noise_removes_image_and_size_attrs() -> None:
    src = '前文\n\n![架构图](media/arch.png){width="3in" height="2in"}\n\n后文'
    out = clean_noise(src)
    assert "![" not in out
    assert "width=" not in out
    assert "前文" in out and "后文" in out


def test_clean_noise_keeps_link_anchor_drops_bare_url() -> None:
    src = "见 [官方文档](http://example.com/docs) 与 [](http://example.com/bare) 结束"
    out = clean_noise(src)
    assert "官方文档" in out
    assert "http://" not in out


def test_clean_noise_underline_keeps_inner_text() -> None:
    out = clean_noise("学习 [关键技术]{.underline} 章节")
    assert "关键技术" in out
    assert "{.underline}" not in out


def test_parser_chapter_path_and_table_list() -> None:
    raw = convert_document_to_raw_text(SAMPLE_MD)
    cleaned = clean_noise(raw)
    parsed = parse_structure(cleaned, fallback_doc_title="sample")
    assert parsed.doc_title
    paths = {u.chapter_path for u in parsed.units if u.chapter_path}
    assert any("概述" in p or "1." in p for p in paths)
    assert any(u.is_table for u in parsed.units)
    assert any(u.is_list_block for u in parsed.units)
    assert any("复杂过程优化" in (u.chapter_path or u.text) for u in parsed.units)


def test_full_pipeline_acceptance(chroma_dir: Path) -> None:
    """验收：无噪音残留、有 chapter_path、杜撰通过、覆盖率≥95%、可去重。"""
    result = run_pipeline(
        SAMPLE_MD,
        doc_id="tpt2_sample",
        persist_dir=chroma_dir,
        embed_fn=hash_embed_texts,
        enable_semantic_dedupe=True,
        write_vectorstore=True,
    )
    assert result.chunks, "应产出 chunk"
    assert "![" not in result.cleaned_text
    assert "{width=" not in result.cleaned_text
    assert all(c.chapter_path for c in result.chunks), "每个 chunk 都应有 chapter_path"
    assert result.quality_report is not None
    assert result.quality_report.fabrication_passed is True
    assert result.quality_report.coverage_ratio >= 0.95
    assert result.quality_report.coverage_passed is True
    # 精确重复段落应被去掉至少 0 或更多
    assert result.quality_report.chunk_count_after <= result.quality_report.chunk_count_before
    # chunk 正文无路径前缀
    for c in result.chunks:
        assert not c.raw_text.startswith("[")
        assert c.chunk_text.startswith("[") or c.chapter_path == ""


def test_fabrication_detects_injected_sentence() -> None:
    result = run_pipeline(
        SAMPLE_MD,
        doc_id="fab_test",
        embed_fn=hash_embed_texts,
        write_vectorstore=False,
    )
    evil = result.chunks[0].model_copy(
        update={"raw_text": result.chunks[0].raw_text + "\n这是原文没有的杜撰建议方向。"}
    )
    ok, fails = check_fabrication([evil], result.cleaned_text)
    assert ok is False
    assert fails


def test_generator_entity_validation_fallback() -> None:
    result = run_pipeline(
        SAMPLE_MD,
        doc_id="gen_test",
        embed_fn=hash_embed_texts,
        write_vectorstore=False,
    )
    chunks = result.chunks[:2]
    # 模拟 LLM 胡编
    answer = generate_answer(
        "TPT 是什么",
        chunks,
        chat_fn=lambda _p: "建议建设量子星舰推进系统并采购 XYZ-999。",
    )
    # 应回退为原文拼接（实体校验失败）
    assert "量子星舰" not in answer or answer == ANSWER_UNAVAILABLE
    assert any(c.raw_text in answer for c in chunks) or answer == ANSWER_UNAVAILABLE


def test_validate_answer_entities_ok() -> None:
    result = run_pipeline(
        SAMPLE_MD,
        doc_id="ent_ok",
        embed_fn=hash_embed_texts,
        write_vectorstore=False,
    )
    chunks = result.chunks
    blob = chunks[0].raw_text
    assert validate_answer_entities(blob[: min(40, len(blob))] or ANSWER_UNAVAILABLE, chunks)


def test_dedupe_exact(chroma_dir: Path) -> None:
    result = run_pipeline(
        SAMPLE_MD,
        doc_id="dedupe",
        persist_dir=chroma_dir,
        embed_fn=hash_embed_texts,
        write_vectorstore=False,
    )
    # 人为塞入完全重复
    dup = result.chunks[0].model_copy(deep=True)
    dup.chunk_id = "x"
    dup.chunk_index = 999
    merged, report = quality_check_and_dedupe(
        result.chunks + [dup],
        source_text=result.cleaned_text,
        embed_fn=hash_embed_texts,
        enable_semantic=False,
    )
    assert report.exact_duplicates_removed >= 1
    assert len(merged) == len(result.chunks)
