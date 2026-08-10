"""数据清洗模块测试。"""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.data_cleaning.splitter import split_plain_text_to_sections
from app.data_cleaning.extract import is_thinking_chain_paragraph
from app.data_cleaning.utils import extract_json_object


class TestSplitter:
    def test_split_by_headings(self):
        long_body = "验证码 5 分钟有效，过期需重新获取。" * 8
        order_body = "订单流程说明。" * 30
        text = f"## 登录\n\n{long_body}\n\n## 订单\n\n{order_body}"
        slices = split_plain_text_to_sections(text)
        assert len(slices) >= 2
        paths = {s.section_path for s in slices}
        assert "登录" in paths
        assert "订单" in paths

    def test_skip_short_blocks(self):
        text = "短\n\n" + ("## 长章节\n\n" + "内容足够长。" * 40)
        slices = split_plain_text_to_sections(text)
        assert all(len(s.raw_text) >= 120 for s in slices)

    def test_merge_docx_style_short_paragraphs(self):
        """模拟 Word 多段短行：应合并后产出切片。"""
        short_para = "这是思维链中的一步说明。"
        text = "\n\n".join([short_para] * 30)
        slices = split_plain_text_to_sections(text)
        assert len(slices) >= 1
        assert sum(len(s.raw_text) for s in slices) >= 120

    def test_thinking_chain_fast_path_marker(self):
        raw = '步骤1\n\n<json>\n{"tool": "AAS", "ability": "查询"}\n</json>'
        assert is_thinking_chain_paragraph(raw)

    def test_tiny_doc_fallback_full_text(self):
        """极短文档不再丢弃：兜底为「全文」一段，避免审核页 0 段。"""
        slices = split_plain_text_to_sections("hi")
        assert len(slices) == 1
        assert slices[0].section_path == "全文"
        assert slices[0].raw_text == "hi"

    def test_short_heading_sections_fallback(self):
        """标题下正文过短时合并兜底。"""
        text = "## A\n\n短\n\n## B\n\n也短"
        slices = split_plain_text_to_sections(text)
        assert len(slices) >= 1
        assert any(s.section_path == "全文" for s in slices)


class TestUtils:
    def test_extract_json_object(self):
        raw = '说明\n{"essence": "hello", "anchor_labels": ["a"]}'
        data = extract_json_object(raw)
        assert data.get("essence") == "hello"


@pytest.mark.asyncio
async def test_create_clean_job(client, auth_headers, default_kb_id):
    """创建清洗任务并入队。"""
    kb_id = default_kb_id

    content = ("## 功能A\n\n" + "这是功能A的详细规则说明。" * 25 + "\n\n").encode("utf-8")
    files = {"file": ("test.md", io.BytesIO(content), "text/markdown")}
    data = {
        "kb_id": kb_id,
        "doc_type": "prd",
        "product": "TestApp",
        "version": "v1",
        "environment": "",
        "note": "",
    }
    with patch("app.data_cleaning.worker._process_job", new_callable=AsyncMock) as mock_proc:
        r = client.post("/api/data-cleaning/jobs", data=data, files=files, headers=auth_headers)
        assert r.status_code == 201
        body = r.json()
        assert body["status"] in ("uploaded", "processing")
        assert body["kb_id"] == kb_id


def test_list_anchors(client, auth_headers):
    r = client.get("/api/data-cleaning/anchors", headers=auth_headers)
    assert r.status_code == 200
    anchors = r.json()
    assert any(a["id"] == "login_sms" for a in anchors)


@pytest.mark.asyncio
async def test_approve_clean_job(client, auth_headers, default_kb_id):
    """批准入库：段落写入 Knowledge Unit。"""
    import uuid

    from app.data_cleaning.models import CleanJob, ParagraphUnit
    from app.data_cleaning.utils import dumps_json
    from app.platform.database import SessionLocal

    kb_id = default_kb_id
    job_id = uuid.uuid4().hex

    db = SessionLocal()
    try:
        job = CleanJob(
            id=job_id,
            kb_id=kb_id,
            user_id=1,
            filename="approve.md",
            original_path=str(Path("tests/fixtures/approve.md")),
            file_size=100,
            doc_type="prd",
            status="pending_review",
            paragraph_count=1,
        )
        db.add(job)
        pid = uuid.uuid4().hex
        db.add(
            ParagraphUnit(
                id=pid,
                job_id=job_id,
                seq=0,
                section_path="登录",
                raw_text="原始段落内容。" * 30,
                essence_markdown="验证码 5 分钟有效。",
                anchor_ids_json=dumps_json(["login_sms"]),
                scope_json=dumps_json({"product": "TestApp"}),
                alignment_json="[]",
                review_status="pending",
                review_action="add",
            )
        )
        db.commit()
    finally:
        db.close()

    fake_vec = [0.01] * 1024
    with (
        patch("app.data_cleaning.ingest.embed_texts", new_callable=AsyncMock, return_value=[fake_vec]),
        patch("app.data_cleaning.ingest.upsert_chunks"),
    ):
        r = client.post(f"/api/data-cleaning/jobs/{job_id}/approve", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["approved_count"] == 1
        assert len(body["ku_ids"]) == 1
