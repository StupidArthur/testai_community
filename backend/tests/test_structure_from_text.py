"""纯文本 → 九维结构化 API 测试。"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from app.skill_hub.bootstrap import ensure_skill_hub_startup
from app.skill_hub.langgpt_meta_bootstrap import ensure_langgpt_meta_skill
from app.skill_hub.platform_skills import LANGGPT_META_SKILL_NAME
from app.skill_hub.service import get_skill_by_name

_MOCK_MD = """```markdown
# Role
测试结构化专家

## Profile
- Author: test

## Background
背景

## Goals
1. 目标一

## Constraints
- 必须遵守

## Core Skills
1. 技能一

## Workflows
1. 步骤一

## Output Format
JSON

## Initialization
就绪
```"""


def test_meta_skill_bootstrapped():
    ensure_skill_hub_startup()
    from app.platform.database import SessionLocal

    db = SessionLocal()
    try:
        skill = get_skill_by_name(db, LANGGPT_META_SKILL_NAME)
        assert skill is not None
        assert skill.display_name
    finally:
        db.close()


class TestStructureFromText:
    def test_structure_from_plain_text(self, client, eng_headers):
        ensure_langgpt_meta_skill()
        with patch(
            "app.skill_hub.service.chat",
            new_callable=AsyncMock,
            return_value=_MOCK_MD,
        ):
            r = client.post(
                "/api/skills/structure-from-text",
                json={"plain_text": "我要做一个登录测试 skill"},
                headers=eng_headers,
            )
        assert r.status_code == 200
        body = r.json()
        assert "测试结构化专家" in body["role"]
        assert body["goals"]
        assert body["raw_markdown"]

    def test_structure_requires_text(self, client, eng_headers):
        r = client.post(
            "/api/skills/structure-from-text",
            json={"plain_text": "  "},
            headers=eng_headers,
        )
        assert r.status_code == 422 or r.status_code == 400
