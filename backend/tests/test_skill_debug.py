"""Skill 调试 API 测试。"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.skill_hub.bootstrap import ensure_skill_hub_startup


@pytest.fixture(autouse=True)
def _skill_hub_ready(client):
    ensure_skill_hub_startup()


def _create_skill(client, headers):
    suffix = uuid.uuid4().hex[:8]
    r = client.post(
        "/api/skills",
        json={
            "name": f"Debug_Test_Skill_{suffix}",
            "display_name": "调试测试",
            "definition": "for debug test",
            "category": "api_testing",
            "tags": [],
        },
        headers=headers,
    )
    assert r.status_code in (200, 201), r.text
    return r.json()


class TestSkillDebug:
    def test_debug_run(self, client, eng_headers):
        skill = _create_skill(client, eng_headers)
        skill_id = skill["id"]

        branches = client.get(f"/api/skills/{skill_id}/branches", headers=eng_headers).json()
        std = next(b for b in branches if b["branch_type"] == "standard")
        versions = client.get(
            f"/api/skills/{skill_id}/branches/{std['id']}/versions",
            headers=eng_headers,
        ).json()
        assert len(versions) >= 1
        vid = versions[0]["id"]

        with patch(
            "app.skill_hub.service.chat",
            new_callable=AsyncMock,
            return_value="这是 Skill 调试输出",
        ):
            r = client.post(
                f"/api/skills/{skill_id}/debug/run",
                json={"user_input": "你好，请自我介绍", "version_id": vid},
                headers=eng_headers,
            )
        assert r.status_code == 200
        body = r.json()
        assert body["output"] == "这是 Skill 调试输出"
        assert body["version_id"] == vid
        assert "payload" in body and len(body["payload"]) > 0

    def test_debug_requires_input(self, client, eng_headers):
        skill = _create_skill(client, eng_headers)
        r = client.post(
            f"/api/skills/{skill['id']}/debug/run",
            json={"user_input": "  "},
            headers=eng_headers,
        )
        assert r.status_code == 422 or r.status_code == 400
