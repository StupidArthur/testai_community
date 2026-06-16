"""tool_hub 列表、筛选与详情。"""
from __future__ import annotations

from .helpers import create_client_tool, create_platform_tool, manual_md, unique_slug


class TestToolHubList:
  def test_list_authenticated(self, client, eng_headers):
    r = client.get("/api/tool-hub/tools", headers=eng_headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)
    assert len(r.json()) >= 2

  def test_filter_by_tool_kind_client(self, client, eng_headers):
    create_client_tool(client, eng_headers)
    r = client.get("/api/tool-hub/tools?tool_kind=client", headers=eng_headers)
    assert r.status_code == 200
    assert all(t["tool_kind"] == "client" for t in r.json())

  def test_filter_by_tool_kind_platform(self, client, eng_headers):
    create_platform_tool(client, eng_headers)
    r = client.get("/api/tool-hub/tools?tool_kind=platform", headers=eng_headers)
    assert r.status_code == 200
    assert all(t["tool_kind"] == "platform" for t in r.json())

  def test_delisted_hidden_from_other_users(self, client, eng_headers, auth_headers):
    tool = create_platform_tool(client, eng_headers)
    tool_id = tool["id"]

    off = client.put(
      f"/api/tool-hub/tools/{tool_id}",
      json={"enabled": False},
      headers=eng_headers,
    )
    assert off.status_code == 200

    admin_list = client.get("/api/tool-hub/tools", headers=auth_headers)
    admin_slugs = {t["slug"] for t in admin_list.json()}
    assert tool["slug"] in admin_slugs

    other_eng = client.post(
      "/api/auth/add-user",
      json={"username": "tool_hub_other", "password": "other123456", "role": "Engineer"},
      headers=auth_headers,
    )
    if other_eng.status_code == 200:
      other_token = other_eng.json()["access_token"]
    else:
      login = client.post(
        "/api/auth/login",
        json={"username": "tool_hub_other", "password": "other123456"},
      )
      other_token = login.json()["access_token"]
    other_headers = {"Authorization": f"Bearer {other_token}"}

    other_list = client.get("/api/tool-hub/tools", headers=other_headers)
    other_slugs = {t["slug"] for t in other_list.json()}
    assert tool["slug"] not in other_slugs


class TestToolHubDetail:
  def test_get_platform_detail(self, client, eng_headers):
    tool = create_platform_tool(client, eng_headers)
    r = client.get(f"/api/tool-hub/tools/{tool['id']}", headers=eng_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["slug"] == tool["slug"]
    assert body["tool_kind"] == "platform"
    assert "使用说明" in body["combined_markdown"]
    assert body["can_edit"] is True
    assert body["can_delete"] is False
    assert len(body["versions"]) >= 1

  def test_get_detail_not_found(self, client, eng_headers):
    r = client.get("/api/tool-hub/tools/00000000-0000-0000-0000-000000000000", headers=eng_headers)
    assert r.status_code == 404

  def test_admin_sees_can_delete_on_others_tool(self, client, eng_headers, auth_headers):
    tool = create_platform_tool(client, eng_headers)
    r = client.get(f"/api/tool-hub/tools/{tool['id']}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["can_delete"] is True
    assert r.json()["can_edit"] is True
