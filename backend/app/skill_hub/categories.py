"""
Skill 分类默认种子与 tags 常量。

分类主数据存 `skill_categories` 表，由 Admin 在 /api/skills/categories 管理；
本文件仅保留首次 seed 与 tags 限制。
"""

from __future__ import annotations

# 首次建库时写入 skill_categories（若表为空）
DEFAULT_SKILL_CATEGORIES: list[tuple[str, str, int]] = [
    ("api_testing", "API 测试", 10),
    ("test_design", "用例设计", 20),
    ("security", "安全测试", 30),
    ("automation", "自动化 / 工具链", 40),
    ("documentation", "文档与规范", 50),
    ("agent_general", "Agent 通用", 60),
    ("other", "其他", 99),
]

MAX_SKILL_TAGS = 8
MAX_TAG_LENGTH = 32


def normalize_tags(raw: list[str] | None) -> list[str]:
    """去重、去空、截断长度，保持顺序。"""
    if not raw:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for item in raw:
        t = (item or "").strip()
        if not t or t in seen:
            continue
        seen.add(t)
        out.append(t[:MAX_TAG_LENGTH])
        if len(out) >= MAX_SKILL_TAGS:
            break
    return out
