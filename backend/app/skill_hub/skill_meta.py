"""
Skill 元数据（category / tags）序列化。
"""
from __future__ import annotations

import json

from app.skill_hub.categories import normalize_tags


def parse_tags_json(raw: str | None) -> list[str]:
    """从 DB JSON 文本解析 tags。"""
    if not raw or not raw.strip():
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return normalize_tags([str(x) for x in data])


def tags_to_json(tags: list[str] | None) -> str:
    """持久化 tags 为 JSON 字符串。"""
    return json.dumps(normalize_tags(tags), ensure_ascii=False)
