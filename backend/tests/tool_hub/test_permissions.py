"""tool_hub 编辑、下架、删除权限。"""
from __future__ import annotations

from .helpers import create_platform_tool, manual_md, unique_slug


class TestToolHubPermissions:
  def test_owner_can_update_metadata(self, client, eng_headers):
    tool = create_platform_tool(client, eng_headers)
    r = client.put(
      f"/api/tool-hub/tools/{tool['id']}",
      json={"display_name": "新名称", "tool_type": "custom"},
      headers=eng_headers,
    )
    assert r.status_code == 200
    assert r.json()["display_name"] == "新名称"
    assert r.json()["tool_type"] == "custom"

  def test_owner_can_update_manual_md(self, client, eng_headers):
    tool = create_platform_tool(client, eng_headers)
    new_manual = "# 更新后的说明\n\n编辑文档测试内容。"
    r = client.put(
      f"/api/tool-hub/tools/{tool['id']}",
      json={"manual_md": new_manual},
      headers=eng_headers,
    )
    assert r.status_code == 200
    assert new_manual in r.json()["combined_markdown"]
    assert r.json()["versions"][0]["manual_md"] == new_manual

  def test_owner_can_delist(self, client, eng_headers):
    tool = create_platform_tool(client, eng_headers)
    r = client.put(
      f"/api/tool-hub/tools/{tool['id']}",
      json={"enabled": False},
      headers=eng_headers,
    )
    assert r.status_code == 200
    assert r.json()["enabled"] is False

  def test_owner_cannot_delete(self, client, eng_headers, auth_headers):
    tool = create_platform_tool(client, eng_headers)
    r = client.delete(f"/api/tool-hub/tools/{tool['id']}", headers=eng_headers)
    assert r.status_code == 403

    admin = client.delete(f"/api/tool-hub/tools/{tool['id']}", headers=auth_headers)
    assert admin.status_code == 204

    gone = client.get(f"/api/tool-hub/tools/{tool['id']}", headers=eng_headers)
    assert gone.status_code == 404

  def test_non_owner_cannot_edit(self, client, eng_headers, auth_headers):
    tool = create_platform_tool(client, eng_headers)
    other = client.post(
      "/api/auth/add-user",
      json={"username": "perm_other", "password": "perm123456", "role": "Engineer"},
      headers=auth_headers,
    )
    if other.status_code == 200:
      token = other.json()["access_token"]
    else:
      token = client.post(
        "/api/auth/login",
        json={"username": "perm_other", "password": "perm123456"},
      ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    r = client.put(
      f"/api/tool-hub/tools/{tool['id']}",
      json={"display_name": "篡改"},
      headers=headers,
    )
    assert r.status_code == 403

  def test_platform_cannot_clear_link_url(self, client, eng_headers):
    tool = create_platform_tool(client, eng_headers, link_url="/translate")
    r = client.put(
      f"/api/tool-hub/tools/{tool['id']}",
      json={"link_url": ""},
      headers=eng_headers,
    )
    assert r.status_code == 400
    assert "跳转链接" in r.json()["detail"]

  def test_admin_can_delete_any_tool(self, client, eng_headers, auth_headers):
    slug = unique_slug("admin_del")
    created = client.post(
      "/api/tool-hub/tools",
      data={
        "slug": slug,
        "display_name": "待删",
        "tool_kind": "platform",
        "link_url": "https://example.com",
        "manual_md": manual_md(),
      },
      headers=eng_headers,
    )
    tool_id = created.json()["id"]
    r = client.delete(f"/api/tool-hub/tools/{tool_id}", headers=auth_headers)
    assert r.status_code == 204
