"""tool_hub 客户端制品下载。"""
from __future__ import annotations

from .helpers import create_client_tool, create_platform_tool, fake_exe, get_tool_by_slug, unique_slug


class TestToolHubDownload:
  def test_download_client_artifact(self, client, eng_headers):
    content = b"MZ downloadable exe content"
    slug = unique_slug("dl_client")
    created = client.post(
      "/api/tool-hub/tools",
      data={
        "slug": slug,
        "display_name": "下载测试",
        "tool_kind": "client",
        "manual_md": "# dl",
      },
      files={"artifact": ("mytool.exe", fake_exe(content), "application/octet-stream")},
      headers=eng_headers,
    )
    assert created.status_code == 201
    tool_id = created.json()["id"]

    r = client.get(f"/api/tool-hub/tools/{tool_id}/download", headers=eng_headers)
    assert r.status_code == 200
    assert r.content == content
    assert "mytool.exe" in r.headers.get("content-disposition", "")

  def test_download_latest_version_after_upgrade(self, client, eng_headers):
    tool = create_client_tool(client, eng_headers, filename="v1.exe")
    tool_id = tool["id"]
    v2_content = b"MZ version two"
    client.post(
      f"/api/tool-hub/tools/{tool_id}/versions",
      data={"version_label": "2.0.0", "changelog_md": "## 2"},
      files={"artifact": ("v2.exe", fake_exe(v2_content), "application/octet-stream")},
      headers=eng_headers,
    )
    r = client.get(f"/api/tool-hub/tools/{tool_id}/download", headers=eng_headers)
    assert r.status_code == 200
    assert r.content == v2_content

  def test_download_platform_tool_rejected(self, client, eng_headers):
    translate = get_tool_by_slug(client, eng_headers, "ai_translate")
    r = client.get(f"/api/tool-hub/tools/{translate['id']}/download", headers=eng_headers)
    assert r.status_code == 400
    assert "仅客户端" in r.json()["detail"]

  def test_download_without_artifact_404(self, client, eng_headers):
    platform = create_platform_tool(client, eng_headers)
    r = client.get(f"/api/tool-hub/tools/{platform['id']}/download", headers=eng_headers)
    assert r.status_code == 400

  def test_download_delisted_forbidden_for_non_owner(self, client, eng_headers, auth_headers):
    tool = create_client_tool(client, eng_headers)
    tool_id = tool["id"]
    client.put(f"/api/tool-hub/tools/{tool_id}", json={"enabled": False}, headers=eng_headers)

    other = client.post(
      "/api/auth/add-user",
      json={"username": "dl_other", "password": "dl123456", "role": "Engineer"},
      headers=auth_headers,
    )
    if other.status_code == 200:
      token = other.json()["access_token"]
    else:
      token = client.post(
        "/api/auth/login",
        json={"username": "dl_other", "password": "dl123456"},
      ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    r = client.get(f"/api/tool-hub/tools/{tool_id}/download", headers=headers)
    assert r.status_code == 404

  def test_owner_can_download_delisted_tool(self, client, eng_headers):
    tool = create_client_tool(client, eng_headers)
    tool_id = tool["id"]
    client.put(f"/api/tool-hub/tools/{tool_id}", json={"enabled": False}, headers=eng_headers)
    r = client.get(f"/api/tool-hub/tools/{tool_id}/download", headers=eng_headers)
    assert r.status_code == 200
