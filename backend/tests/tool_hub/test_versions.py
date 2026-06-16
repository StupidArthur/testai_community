"""tool_hub 版本发布与 Markdown 合并。"""
from __future__ import annotations

from .helpers import create_client_tool, create_platform_tool, fake_exe, manual_md


class TestToolHubVersions:
  def test_add_client_version_with_changelog(self, client, eng_headers):
    tool = create_client_tool(client, eng_headers)
    tool_id = tool["id"]

    r = client.post(
      f"/api/tool-hub/tools/{tool_id}/versions",
      data={
        "version_label": "2.0.0",
        "changelog_md": "## 2.0.0\n\n- 修复若干问题",
      },
      files={"artifact": ("v2.exe", fake_exe(b"MZ v2"), "application/octet-stream")},
      headers=eng_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["latest_version"] == "2.0.0"
    assert "2.0.0" in body["combined_markdown"]
    assert "版本更新记录" in body["combined_markdown"]
    assert len(body["versions"]) == 2

  def test_client_version_requires_artifact(self, client, eng_headers):
    tool = create_client_tool(client, eng_headers)
    r = client.post(
      f"/api/tool-hub/tools/{tool['id']}/versions",
      data={
        "version_label": "2.0.0",
        "changelog_md": "## 2.0.0\n\n- 无文件",
      },
      headers=eng_headers,
    )
    assert r.status_code == 400
    assert "须上传文件" in r.json()["detail"]

  def test_platform_version_without_artifact(self, client, eng_headers):
    tool = create_platform_tool(client, eng_headers)
    r = client.post(
      f"/api/tool-hub/tools/{tool['id']}/versions",
      data={
        "version_label": "1.1.0",
        "changelog_md": "## 1.1.0\n\n- 文档更新",
        "manual_md": manual_md("更新说明"),
      },
      headers=eng_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["latest_version"] == "1.1.0"
    assert "1.1.0" in body["combined_markdown"]

  def test_version_inherits_manual_when_omitted(self, client, eng_headers):
    tool = create_client_tool(client, eng_headers)
    original_manual = tool["combined_markdown"]
    r = client.post(
      f"/api/tool-hub/tools/{tool['id']}/versions",
      data={
        "version_label": "1.0.1",
        "changelog_md": "## 1.0.1\n\n- patch",
      },
      files={"artifact": ("patch.exe", fake_exe(b"MZ patch"), "application/octet-stream")},
      headers=eng_headers,
    )
    assert r.status_code == 200
    assert "使用说明" in r.json()["combined_markdown"]
    assert original_manual.split("使用说明")[1][:20] in r.json()["combined_markdown"]

  def test_add_version_forbidden_for_non_owner(self, client, eng_headers, auth_headers):
    tool = create_platform_tool(client, eng_headers)
    other = client.post(
      "/api/auth/add-user",
      json={"username": "ver_other", "password": "ver123456", "role": "Engineer"},
      headers=auth_headers,
    )
    if other.status_code == 200:
      token = other.json()["access_token"]
    else:
      token = client.post(
        "/api/auth/login",
        json={"username": "ver_other", "password": "ver123456"},
      ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    r = client.post(
      f"/api/tool-hub/tools/{tool['id']}/versions",
      data={"version_label": "9.9.9", "changelog_md": "hack"},
      headers=headers,
    )
    assert r.status_code == 403
