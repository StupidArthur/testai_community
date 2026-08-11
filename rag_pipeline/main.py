"""
FastAPI 入口。

- POST /documents/upload
- GET /documents/{doc_id}/status
- POST /qa/ask

入口不使用命令行参数传参。
"""

from __future__ import annotations

import logging
import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from rag_pipeline.models.schemas import DocumentStatus, utc_now_iso
from rag_pipeline.pipeline.pipeline import run_pipeline
from rag_pipeline.qa.generator import generate_answer
from rag_pipeline.qa.retriever import retrieve_chunks
from rag_pipeline.vectorstore.embeddings import embed_texts, hash_embed_texts

log = logging.getLogger(__name__)

app = FastAPI(title="RAG Pipeline", version="0.2.0")

_DOC_STATUS: dict[str, DocumentStatus] = {}


class AskRequest(BaseModel):
    """知识问答请求。"""

    question: str = Field(..., min_length=1)


class AskResponse(BaseModel):
    """知识问答响应。"""

    answer: str
    chunk_ids: list[str] = Field(default_factory=list)


def _default_embed_fn():
    """优先真实 Ollama embedding，失败由 store/retriever 内部再降级。"""
    return embed_texts


@app.post("/documents/upload")
async def upload_document(file: UploadFile = File(...)) -> dict:
    """上传文档并触发完整 pipeline。"""
    suffix = Path(file.filename or "upload.bin").suffix.lower()
    doc_id = uuid.uuid4().hex
    status = DocumentStatus(doc_id=doc_id, status="processing", message="pipeline running")
    _DOC_STATUS[doc_id] = status

    tmp_dir = Path(tempfile.mkdtemp(prefix="rag_upload_"))
    original_name = Path(file.filename or f"upload{suffix}").name
    # 保留原始文件名作 doc_title；doc_id 仅作目录前缀防冲突
    dest = tmp_dir / f"{doc_id}_{original_name}"
    dest.write_bytes(await file.read())

    try:
        # 上传路径尽量用真实 embed；不可用时 pipeline/store 会降级 hash
        try:
            embed_fn = _default_embed_fn()
            # 探测一次
            embed_fn(["ping"])
        except Exception:  # noqa: BLE001
            embed_fn = hash_embed_texts

        result = run_pipeline(
            dest,
            doc_id=doc_id,
            doc_title=Path(original_name).stem,
            embed_fn=embed_fn,
            write_vectorstore=True,
        )
        status.status = "completed"
        status.message = "pipeline completed"
        status.chunk_count = len(result.chunks)
        status.quality_report = result.quality_report
        status.updated_at = utc_now_iso()
        return {
            "doc_id": doc_id,
            "status": status.status,
            "message": status.message,
            "raw_chars": len(result.raw_text),
            "cleaned_chars": len(result.cleaned_text),
            "chunk_count": status.chunk_count,
            "doc_summary": result.doc_summary,
            "quality_report": result.quality_report.model_dump() if result.quality_report else None,
        }
    except Exception as exc:  # noqa: BLE001
        log.exception("upload failed: %s", doc_id)
        status.status = "failed"
        status.message = str(exc)
        status.updated_at = utc_now_iso()
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/documents/{doc_id}/status")
async def get_document_status(doc_id: str) -> DocumentStatus:
    """查询处理状态和质检报告。"""
    status = _DOC_STATUS.get(doc_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"doc_id not found: {doc_id}")
    return status


@app.post("/qa/ask")
async def ask_qa(body: AskRequest) -> AskResponse:
    """知识问答：检索 + LLM 组织语言 + 实体校验。"""
    try:
        try:
            embed_fn = embed_texts
            embed_fn(["ping"])
        except Exception:  # noqa: BLE001
            embed_fn = hash_embed_texts
        chunks = retrieve_chunks(body.question, embed_fn=embed_fn)
        answer = generate_answer(body.question, chunks)
        return AskResponse(answer=answer, chunk_ids=[c.chunk_id for c in chunks])
    except Exception as exc:  # noqa: BLE001
        log.exception("ask failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def main() -> None:
    """开发启动。"""
    import uvicorn

    uvicorn.run("rag_pipeline.main:app", host="127.0.0.1", port=48021, reload=False)


if __name__ == "__main__":
    main()
