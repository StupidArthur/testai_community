"""knowledge_base API 测试（Mock Ollama / RAG）。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture()
def kb_headers(auth_headers):
    return auth_headers


def test_create_and_list_knowledge_base(client, kb_headers, eng_headers):
    r = client.post(
        "/api/knowledge-base/bases",
        json={"name": "测试库", "description": "pytest"},
        headers=kb_headers,
    )
    assert r.status_code == 201
    kb_id = r.json()["id"]

    # 工程师也能看到全站知识库
    r2 = client.get("/api/knowledge-base/bases", headers=eng_headers)
    assert r2.status_code == 200
    ids = [b["id"] for b in r2.json()]
    assert kb_id in ids

    r3 = client.get(f"/api/knowledge-base/bases/{kb_id}", headers=eng_headers)
    assert r3.status_code == 200
    assert r3.json()["name"] == "测试库"


def test_upload_markdown_document(client, kb_headers, tmp_path):
    r = client.post(
        "/api/knowledge-base/bases",
        json={"name": "上传测试"},
        headers=kb_headers,
    )
    kb_id = r.json()["id"]
    md_content = "# 标题\n\n这是知识库测试文档内容。\n\n## 第二节\n\n更多文字用于分块。"

    with patch(
        "app.knowledge_base.worker.process_document_to_chunks",
        new_callable=AsyncMock,
    ) as mock_process, patch(
        "app.knowledge_base.worker.embed_texts",
        new_callable=AsyncMock,
    ) as mock_embed, patch(
        "app.knowledge_base.worker.upsert_chunks",
    ), patch(
        "app.knowledge_base.worker.delete_document_chunks",
    ):
        from app.ai_service.document.schemas import DocumentProcessResult

        mock_process.return_value = (
            DocumentProcessResult(filename="test.md", plain_text=md_content, blocks=[]),
            [
                {
                    "id": "c1",
                    "text": md_content,
                    "metadata": {"page": -1, "block_type": "text", "source": "test.md"},
                }
            ],
        )
        mock_embed.return_value = [[0.1, 0.2, 0.3]]

        files = {"file": ("test.md", md_content.encode("utf-8"), "text/markdown")}
        r_up = client.post(
            f"/api/knowledge-base/bases/{kb_id}/documents",
            files=files,
            headers=kb_headers,
        )
        assert r_up.status_code == 201
        assert r_up.json()["user_id"] is not None
        doc_id = r_up.json()["id"]

        import asyncio
        from app.knowledge_base.worker import _process_document

        asyncio.run(_process_document(doc_id))

    r_detail = client.get(f"/api/knowledge-base/bases/{kb_id}", headers=kb_headers)
    docs = r_detail.json()["documents"]
    assert any(d["id"] == doc_id and d["status"] == "ready" for d in docs)


def test_document_delete_permission(client, kb_headers, eng_headers):
    r = client.post(
        "/api/knowledge-base/bases",
        json={"name": "权限测试"},
        headers=kb_headers,
    )
    kb_id = r.json()["id"]

    from app.platform.database import SessionLocal
    from app.knowledge_base.models import KnowledgeDocument

    db = SessionLocal()
    try:
        admin_user = __import__("app.auth.models", fromlist=["User"]).User
        admin = db.query(admin_user).filter(admin_user.username == "admin").first()
        doc = KnowledgeDocument(
            id="doc_perm_test",
            kb_id=kb_id,
            user_id=admin.id,
            filename="admin.md",
            original_path=str(Path("admin.md")),
            file_size=10,
            status="ready",
        )
        db.add(doc)
        db.commit()
    finally:
        db.close()

    # 工程师不能删 admin 上传的文档
    with patch("app.knowledge_base.service.delete_document_chunks"):
        r_del = client.delete(
            f"/api/knowledge-base/bases/{kb_id}/documents/doc_perm_test",
            headers=eng_headers,
        )
    assert r_del.status_code == 403

    # admin 可以删
    with patch("app.knowledge_base.service.delete_document_chunks"):
        r_del2 = client.delete(
            f"/api/knowledge-base/bases/{kb_id}/documents/doc_perm_test",
            headers=kb_headers,
        )
    assert r_del2.status_code == 204


def test_chat_rag(client, kb_headers):
    r = client.post(
        "/api/knowledge-base/bases",
        json={"name": "对话测试"},
        headers=kb_headers,
    )
    kb_id = r.json()["id"]

    from app.platform.database import SessionLocal
    from app.knowledge_base.models import KnowledgeDocument

    db = SessionLocal()
    try:
        admin_user = __import__("app.auth.models", fromlist=["User"]).User
        admin = db.query(admin_user).filter(admin_user.username == "admin").first()
        doc = KnowledgeDocument(
            id="doc_chat_test",
            kb_id=kb_id,
            user_id=admin.id,
            filename="fake.md",
            original_path=str(Path("fake.md")),
            file_size=10,
            status="ready",
            chunk_count=1,
        )
        db.add(doc)
        db.commit()
    finally:
        db.close()

    with patch(
        "app.knowledge_base.service.answer_with_rag",
        new_callable=AsyncMock,
    ) as mock_rag:
        mock_rag.return_value = {
            "answer": "这是基于资料的测试回答。",
            "citations": [{"filename": "fake.md", "snippet": "测试", "page": None}],
            "hits": [],
        }
        r_chat = client.post(
            f"/api/knowledge-base/bases/{kb_id}/chat",
            json={"question": "测试问题"},
            headers=kb_headers,
        )
        assert r_chat.status_code == 200
        assert "测试回答" in r_chat.json()["answer"]
