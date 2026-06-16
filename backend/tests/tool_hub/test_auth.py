"""tool_hub 认证与未授权访问。"""
from __future__ import annotations


class TestToolHubAuth:
  def test_list_tools_no_auth(self, client):
    r = client.get("/api/tool-hub/tools")
    assert r.status_code == 401

  def test_get_tool_no_auth(self, client):
    r = client.get("/api/tool-hub/tools/nonexistent-id")
    assert r.status_code == 401

  def test_create_tool_no_auth(self, client):
    r = client.post(
      "/api/tool-hub/tools",
      data={
        "slug": "no_auth_tool",
        "display_name": "x",
        "tool_kind": "platform",
        "link_url": "/translate",
        "manual_md": "# x",
      },
    )
    assert r.status_code == 401

  def test_download_no_auth(self, client):
    r = client.get("/api/tool-hub/tools/nonexistent-id/download")
    assert r.status_code == 401

  def test_delete_no_auth(self, client):
    r = client.delete("/api/tool-hub/tools/nonexistent-id")
    assert r.status_code == 401
