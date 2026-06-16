"""
知识库全链路集成测试（API 层，Mock Ollama/Chroma 写库阶段）。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.ai_service.document.schemas import DocumentProcessResult


@pytest.fixture()
def kb_id(client, auth_headers):
    r = client.post(
        "/api/knowledge-base/bases",
        json={"name": "集成测试库", "description": "e2e"},
        headers=auth_headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_full_knowledge_base_flow(client, auth_headers, eng_headers, kb_id):
    """创建 → 列表 → 上传 → 处理 → 对话 → 删文档 → 删库。"""
    r_list = client.get("/api/knowledge-base/bases", headers=eng_headers)
    assert r_list.status_code == 200
    assert any(b["id"] == kb_id for b in r_list.json())

    r_detail = client.get(f"/api/knowledge-base/bases/{kb_id}", headers=auth_headers)
    assert r_detail.status_code == 200
    assert r_detail.json()["name"] == "集成测试库"

    md = "# 集成测试\n\nRAG 问答验证用段落内容。" * 20

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
        mock_process.return_value = (
            DocumentProcessResult(filename="flow.md", plain_text=md, blocks=[]),
            [{"id": "c1", "text": md, "metadata": {"page": -1, "block_type": "text", "source": "flow.md"}}],
        )
        mock_embed.return_value = [[0.1, 0.2, 0.3]]

        files = {"file": ("flow.md", md.encode("utf-8"), "text/markdown")}
        r_up = client.post(
            f"/api/knowledge-base/bases/{kb_id}/documents",
            files=files,
            headers=eng_headers,
        )
        assert r_up.status_code == 201, r_up.text
        doc_id = r_up.json()["id"]

        import asyncio
        from app.knowledge_base.worker import _process_document

        asyncio.run(_process_document(doc_id))

    r_docs = client.get(f"/api/knowledge-base/bases/{kb_id}", headers=auth_headers)
    docs = r_docs.json()["documents"]
    assert any(d["id"] == doc_id and d["status"] == "ready" for d in docs)

    with patch(
        "app.knowledge_base.service.answer_with_rag",
        new_callable=AsyncMock,
    ) as mock_rag:
        mock_rag.return_value = {
            "answer": "集成测试回答",
            "citations": [{"filename": "flow.md", "snippet": "验证", "page": None}],
            "hits": [],
        }
        r_chat = client.post(
            f"/api/knowledge-base/bases/{kb_id}/chat",
            json={"question": "文档讲了什么？"},
            headers=eng_headers,
        )
        assert r_chat.status_code == 200
        assert "集成测试回答" in r_chat.json()["answer"]

    r_msgs = client.get(f"/api/knowledge-base/bases/{kb_id}/messages", headers=eng_headers)
    assert r_msgs.status_code == 200
    assert len(r_msgs.json()) >= 2

    with patch("app.knowledge_base.service.delete_document_chunks"):
        r_del_doc = client.delete(
            f"/api/knowledge-base/bases/{kb_id}/documents/{doc_id}",
            headers=eng_headers,
        )
    assert r_del_doc.status_code == 204

    with patch("app.knowledge_base.service.delete_kb_collection"):
        r_del_kb = client.delete(f"/api/knowledge-base/bases/{kb_id}", headers=auth_headers)
    assert r_del_kb.status_code == 204
