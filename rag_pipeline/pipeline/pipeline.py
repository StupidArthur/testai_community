"""
串联 Pipeline 五个阶段 + 向量入库。

入库全流程禁止调用 LLM 生成正文；仅允许 Embedding 向量化。
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from rag_pipeline.models.schemas import PipelineResult
from rag_pipeline.pipeline.annotator import annotate_chunks
from rag_pipeline.pipeline.chunker import split_to_chunks
from rag_pipeline.pipeline.cleaner import clean_noise
from rag_pipeline.pipeline.converter import convert_document_to_raw_text
from rag_pipeline.pipeline.parser import parse_structure
from rag_pipeline.pipeline.qa import quality_check_and_dedupe
from rag_pipeline.vectorstore.embeddings import EmbedFn, hash_embed_texts
from rag_pipeline.vectorstore.store import upsert_chunks

log = logging.getLogger(__name__)


def run_pipeline(
    file_path: str | Path,
    *,
    doc_id: str | None = None,
    doc_title: str | None = None,
    persist_dir: Path | None = None,
    embed_fn: EmbedFn | None = None,
    enable_semantic_dedupe: bool = True,
    write_vectorstore: bool = True,
) -> PipelineResult:
    """
    执行文档清洗切片 Pipeline。

    参数：
        file_path: 上传文档本地路径
        doc_id: 可选文档 ID
        doc_title: 可选文档标题（默认取文件名 stem）
        persist_dir: Chroma 目录（测试可隔离）
        embed_fn: 可注入的向量函数（测试用 hash）
        enable_semantic_dedupe: 是否做语义去重
        write_vectorstore: 是否写入向量库
    """
    path = Path(file_path)
    resolved_doc_id = (doc_id or uuid.uuid4().hex).strip()
    fallback_title = (doc_title or path.stem).strip() or path.stem

    # 阶段零
    raw_text = convert_document_to_raw_text(path)
    log.info("stage0 convert: doc_id=%s chars=%s", resolved_doc_id, len(raw_text))

    # 阶段一
    cleaned_text = clean_noise(raw_text)
    log.info("stage1 clean: chars=%s", len(cleaned_text))

    # 阶段二
    parsed = parse_structure(cleaned_text, fallback_doc_title=fallback_title)
    log.info("stage2 parse: units=%s title=%s", len(parsed.units), parsed.doc_title)

    # 阶段三
    chunks = split_to_chunks(
        parsed.units,
        doc_id=resolved_doc_id,
        doc_title=parsed.doc_title,
    )
    log.info("stage3 chunk: count=%s", len(chunks))

    # 阶段四
    chunks, doc_summary = annotate_chunks(chunks, parse_result=parsed)
    log.info("stage4 annotate: summary=%s", doc_summary[:80])

    # 阶段五（Embedding 仅向量化，不生成正文）
    if embed_fn is None:
        try:
            from rag_pipeline.vectorstore.embeddings import embed_texts as _embed_texts

            _embed_texts(["ping"])
            emb: EmbedFn = _embed_texts
        except Exception:  # noqa: BLE001
            emb = hash_embed_texts
    else:
        emb = embed_fn
    chunks, report = quality_check_and_dedupe(
        chunks,
        source_text=cleaned_text,
        embed_fn=emb,
        enable_semantic=enable_semantic_dedupe,
    )
    # 去重后保证摘要挂在 index=0
    if chunks:
        chunks[0].doc_summary = doc_summary
        for c in chunks[1:]:
            c.doc_summary = None
        # 邻接已在 dedupe 内更新
    log.info(
        "stage5 qa: fab=%s coverage=%.3f before=%s after=%s",
        report.fabrication_passed,
        report.coverage_ratio,
        report.chunk_count_before,
        report.chunk_count_after,
    )

    if write_vectorstore and chunks:
        n = upsert_chunks(chunks, embed_fn=emb, persist_dir=persist_dir)
        log.info("vectorstore upsert: %s", n)

    return PipelineResult(
        doc_id=resolved_doc_id,
        doc_title=parsed.doc_title,
        raw_text=raw_text,
        cleaned_text=cleaned_text,
        chunks=chunks,
        quality_report=report,
        doc_summary=doc_summary,
    )


def main() -> None:
    """本地冒烟。"""
    sample = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "sample.md"
    out_dir = Path(__file__).resolve().parents[1] / ".data" / "chroma_smoke"
    result = run_pipeline(
        sample,
        doc_id="sample_md",
        persist_dir=out_dir,
        embed_fn=hash_embed_texts,
        write_vectorstore=True,
    )
    print(
        f"[pipeline] doc_id={result.doc_id} chunks={len(result.chunks)} "
        f"fab={result.quality_report.fabrication_passed if result.quality_report else None} "
        f"cov={result.quality_report.coverage_ratio if result.quality_report else None}"
    )
    for c in result.chunks[:5]:
        print(f"  - {c.chunk_id} path={c.chapter_path!r} len={len(c.raw_text)}")


if __name__ == "__main__":
    main()
