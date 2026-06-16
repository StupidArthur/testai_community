"""tool_hub 启动预置与 bootstrap 行为。"""
from __future__ import annotations

from app.platform.database import engine
from app.tool_hub.bootstrap import ensure_tool_hub_startup

from .helpers import get_tool_by_slug


class TestToolHubBootstrap:
  def test_list_includes_builtin_translate_and_recorder(self, client, eng_headers):
    r = client.get("/api/tool-hub/tools", headers=eng_headers)
    assert r.status_code == 200
    slugs = {t["slug"] for t in r.json()}
    assert "ai_translate" in slugs
    assert "feature_recorder" in slugs

  def test_ai_translate_is_platform_with_link(self, client, eng_headers):
    card = get_tool_by_slug(client, eng_headers, "ai_translate")
    assert card is not None
    assert card["tool_kind"] == "platform"
    assert card["link_url"] == "/translate"
    assert card["enabled"] is True

  def test_feature_recorder_is_client(self, client, eng_headers):
    card = get_tool_by_slug(client, eng_headers, "feature_recorder")
    assert card is not None
    assert card["tool_kind"] == "client"
    assert card["enabled"] is True

  def test_builtin_detail_has_manual_markdown(self, client, eng_headers):
    translate = get_tool_by_slug(client, eng_headers, "ai_translate")
    r = client.get(f"/api/tool-hub/tools/{translate['id']}", headers=eng_headers)
    assert r.status_code == 200
    body = r.json()
    assert "使用说明" in body["combined_markdown"] or "AI 翻译" in body["combined_markdown"]
    assert body["can_edit"] is False
    assert body["can_delete"] is False

  def test_bootstrap_idempotent(self, client, eng_headers):
    ensure_tool_hub_startup(engine)
    ensure_tool_hub_startup(engine)
    r = client.get("/api/tool-hub/tools", headers=eng_headers)
    slugs = [t["slug"] for t in r.json()]
    assert slugs.count("ai_translate") == 1
    assert slugs.count("feature_recorder") == 1
