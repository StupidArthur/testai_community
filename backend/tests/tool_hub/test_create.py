"""tool_hub 创建工具与参数校验。"""
from __future__ import annotations

import io

from .helpers import fake_exe, fake_zip, manual_md, unique_slug


class TestToolHubCreatePlatform:
  def test_create_platform_success(self, client, eng_headers):
    slug = unique_slug("demo_platform")
    r = client.post(
      "/api/tool-hub/tools",
      data={
        "slug": slug,
        "display_name": "演示平台工具",
        "tool_kind": "platform",
        "tool_type": "default",
        "link_url": "/translate",
        "version_label": "1.0.0",
        "manual_md": manual_md(),
      },
      headers=eng_headers,
    )
    assert r.status_code == 201
    body = r.json()
    assert body["slug"] == slug
    assert body["tool_kind"] == "platform"
    assert body["link_url"] == "/translate"
    assert "使用说明" in body["combined_markdown"]
    assert body["has_artifact"] is False

  def test_platform_requires_link_url(self, client, eng_headers):
    r = client.post(
      "/api/tool-hub/tools",
      data={
        "slug": unique_slug("no_link"),
        "display_name": "无链接",
        "tool_kind": "platform",
        "manual_md": manual_md(),
      },
      headers=eng_headers,
    )
    assert r.status_code == 400
    assert "跳转链接" in r.json()["detail"]

  def test_duplicate_slug_rejected(self, client, eng_headers):
    slug = unique_slug("dup")
    payload = {
      "slug": slug,
      "display_name": "A",
      "tool_kind": "platform",
      "link_url": "https://example.com",
      "manual_md": manual_md(),
    }
    r1 = client.post("/api/tool-hub/tools", data=payload, headers=eng_headers)
    assert r1.status_code == 201
    r2 = client.post("/api/tool-hub/tools", data=payload, headers=eng_headers)
    assert r2.status_code == 400
    assert "已存在" in r2.json()["detail"]

  def test_invalid_slug_rejected(self, client, eng_headers):
    r = client.post(
      "/api/tool-hub/tools",
      data={
        "slug": "Bad-Slug",
        "display_name": "x",
        "tool_kind": "platform",
        "link_url": "/x",
        "manual_md": manual_md(),
      },
      headers=eng_headers,
    )
    assert r.status_code == 400


class TestToolHubCreateClient:
  def test_create_client_with_exe(self, client, eng_headers):
    slug = unique_slug("demo_client")
    r = client.post(
      "/api/tool-hub/tools",
      data={
        "slug": slug,
        "display_name": "演示客户端",
        "tool_kind": "client",
        "manual_md": manual_md(),
      },
      files={"artifact": ("demo.exe", fake_exe(), "application/octet-stream")},
      headers=eng_headers,
    )
    assert r.status_code == 201
    body = r.json()
    assert body["tool_kind"] == "client"
    assert body["has_artifact"] is True

  def test_create_client_with_zip(self, client, eng_headers):
    slug = unique_slug("zip_client")
    r = client.post(
      "/api/tool-hub/tools",
      data={
        "slug": slug,
        "display_name": "Zip 客户端",
        "tool_kind": "client",
        "manual_md": manual_md(),
      },
      files={"artifact": ("tool.zip", fake_zip(), "application/zip")},
      headers=eng_headers,
    )
    assert r.status_code == 201
    assert r.json()["has_artifact"] is True

  def test_client_requires_artifact(self, client, eng_headers):
    r = client.post(
      "/api/tool-hub/tools",
      data={
        "slug": unique_slug("no_file"),
        "display_name": "无文件",
        "tool_kind": "client",
        "manual_md": manual_md(),
      },
      headers=eng_headers,
    )
    assert r.status_code == 400
    assert "可执行文件" in r.json()["detail"]

  def test_client_rejects_invalid_extension(self, client, eng_headers):
    r = client.post(
      "/api/tool-hub/tools",
      data={
        "slug": unique_slug("bad_ext"),
        "display_name": "错误扩展名",
        "tool_kind": "client",
        "manual_md": manual_md(),
      },
      files={"artifact": ("readme.txt", io.BytesIO(b"text"), "text/plain")},
      headers=eng_headers,
    )
    assert r.status_code == 400
    assert "不支持的文件类型" in r.json()["detail"]
