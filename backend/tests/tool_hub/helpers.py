"""
tool_hub 测试辅助函数（非 fixture）。
"""
from __future__ import annotations

import io
import uuid
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "tool_hub"


def manual_md(title: str = "测试工具") -> str:
  """生成最小 Markdown 说明书。"""
  return f"# {title}\n\n这是测试工具说明书。"


def unique_slug(prefix: str = "test_tool") -> str:
  """生成合法且唯一的工具 slug。"""
  return f"{prefix}_{uuid.uuid4().hex[:8]}"


def fake_exe(content: bytes = b"MZ fake exe for pytest") -> io.BytesIO:
  """模拟客户端 exe 制品。"""
  return io.BytesIO(content)


def fake_zip(content: bytes | None = None) -> io.BytesIO:
  """模拟客户端 zip 制品。"""
  payload = content or b"PK\x03\x04 fake zip content"
  return io.BytesIO(payload)


def create_platform_tool(client, headers, *, slug: str | None = None, link_url: str = "/translate"):
  """通过 API 创建平台集成工具，返回响应 JSON。"""
  slug = slug or unique_slug("platform")
  r = client.post(
    "/api/tool-hub/tools",
    data={
      "slug": slug,
      "display_name": f"平台工具 {slug}",
      "tool_kind": "platform",
      "tool_type": "default",
      "link_url": link_url,
      "version_label": "1.0.0",
      "manual_md": manual_md(slug),
    },
    headers=headers,
  )
  assert r.status_code == 201, r.text
  return r.json()


def create_client_tool(client, headers, *, slug: str | None = None, filename: str = "demo.exe"):
  """通过 API 创建客户端工具，返回响应 JSON。"""
  slug = slug or unique_slug("client")
  r = client.post(
    "/api/tool-hub/tools",
    data={
      "slug": slug,
      "display_name": f"客户端工具 {slug}",
      "tool_kind": "client",
      "tool_type": "default",
      "version_label": "1.0.0",
      "manual_md": manual_md(slug),
    },
    files={"artifact": (filename, fake_exe(), "application/octet-stream")},
    headers=headers,
  )
  assert r.status_code == 201, r.text
  return r.json()


def get_tool_by_slug(client, headers, slug: str) -> dict | None:
  """从列表中按 slug 查找工具卡片。"""
  r = client.get("/api/tool-hub/tools", headers=headers)
  assert r.status_code == 200
  for item in r.json():
    if item["slug"] == slug:
      return item
  return None
