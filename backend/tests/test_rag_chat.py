"""RAG chat 模块单元测试（不依赖 Ollama / Chroma / MiniMax）。"""

from __future__ import annotations

from app.ai_service.rag.chat import (
    _build_context,
    _build_retrieval_query,
    _detect_scope,
    _is_source_attribution_question,
    _rerank_hits_by_scope,
)


def test_build_context_includes_filename_and_page():
    hits = [
        {
            "text": "单用户响应 < 500ms",
            "metadata": {"filename": "性能报告.docx", "page": 3},
        }
    ]
    ctx = _build_context(hits)
    assert "性能报告.docx" in ctx
    assert "第3页" in ctx
    assert "500ms" in ctx


def test_detect_scope_http_api():
    assert _detect_scope("HTTP请求登录的具体测试数据") == "http_api"
    assert _detect_scope("前端登录页面首次加载耗时") == "frontend_page"


def test_rerank_prefers_api_chunks_for_api_question():
    hits = [
        {"text": "前端登录页面首次加载 1.29s，字体 8.5MB", "distance": 0.1, "metadata": {}},
        {"text": "HTTP 登录接口 500 并发平均 8.2s", "distance": 0.15, "metadata": {}},
    ]
    ranked = _rerank_hits_by_scope(hits, "HTTP请求登录的性能测试数据")
    assert "HTTP 登录接口" in ranked[0]["text"]


def test_retrieval_query_expands_followup_with_history():
    history = [
        {"role": "user", "content": "HTTP请求登录的具体测试数据是什么"},
        {"role": "assistant", "content": "500并发平均8.2s，参考 TPT Saas性能测试报告.docx"},
    ]
    q = _build_retrieval_query("前端登录页面加载的数据是哪里的", history)
    assert "前端登录页面加载的数据是哪里的" in q
    assert "TPT Saas" in q
    assert "请查找上述内容出自哪份文档" in q


def test_source_attribution_question_detected():
    assert _is_source_attribution_question("前端登录页面加载的数据是哪里的")
    assert not _is_source_attribution_question("HTTP请求登录的具体测试数据")
