"""Skill 按 name 调用 API 测试。"""
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
    name = f"Invoke_Test_{suffix}"
    r = client.post(
        "/api/skills",
        json={
            "name": name,
            "display_name": "调用测试",
            "definition": "for invoke test",
            "category": "other",
            "tags": [],
        },
        headers=headers,
    )
    assert r.status_code in (200, 201), r.text
    return name, r.json()


class TestSkillInvokeByName:
    def test_get_payload_by_name_fallback_standard(self, client, eng_headers):
        """master 无版本时，按 name 获取应回退 standard 的 Markdown。"""
        name, skill = _create_skill(client, eng_headers)
        r = client.get(f"/api/skills/by-name/{name}", headers=eng_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["skill_name"] == name
        assert body["branch_type"] == "standard"
        assert body["payload"]
        assert "# Role" in body["payload"]

    def test_get_payload_by_name_master_after_merge(self, client, eng_headers, auth_headers):
        name, skill = _create_skill(client, eng_headers)
        skill_id = skill["id"]
        branches = client.get(f"/api/skills/{skill_id}/branches", headers=eng_headers).json()
        std = next(b for b in branches if b["branch_type"] == "standard")
        versions = client.get(
            f"/api/skills/{skill_id}/branches/{std['id']}/versions",
            headers=eng_headers,
        ).json()
        vid = versions[0]["id"]

        merge_r = client.post(
            f"/api/skills/{skill_id}/merge",
            json={"source_version_id": vid, "commit_message": "publish"},
            headers=auth_headers,
        )
        assert merge_r.status_code == 200

        r = client.get(f"/api/skills/by-name/{name}", headers=eng_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["branch_type"] == "master"
        assert body["version_id"] == merge_r.json()["id"]

    def test_invoke_by_name(self, client, eng_headers):
        name, _ = _create_skill(client, eng_headers)
        with patch(
            "app.skill_hub.service.chat",
            new_callable=AsyncMock,
            return_value="invoke output",
        ):
            r = client.post(
                f"/api/skills/by-name/{name}/invoke",
                json={"user_input": "你好"},
                headers=eng_headers,
            )
        assert r.status_code == 200
        body = r.json()
        assert body["output"] == "invoke output"
        assert body["skill_name"] == name
        assert body["payload"]

    def test_invoke_unknown_skill(self, client, eng_headers):
        r = client.post(
            "/api/skills/by-name/not_exist_skill_xyz/invoke",
            json={"user_input": "hi"},
            headers=eng_headers,
        )
        assert r.status_code == 404
