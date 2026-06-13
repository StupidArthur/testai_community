"""skill_hub 模块 API 测试。"""

import uuid

import pytest


def _unique_skill_name() -> str:
    return f"test_skill_{uuid.uuid4().hex[:8]}"


class TestSkillHubList:
    def test_list_skills_authenticated(self, client, auth_headers):
        r = client.get("/api/skills", headers=auth_headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_list_skills_no_auth(self, client):
        r = client.get("/api/skills")
        assert r.status_code == 401


class TestSkillHubCreate:
    def test_create_skill(self, client, auth_headers):
        name = _unique_skill_name()
        r = client.post(
            "/api/skills",
            json={
                "name": name,
                "display_name": "测试 Skill",
                "definition": "单元测试用",
            },
            headers=auth_headers,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["name"] == name
        skill_id = body["id"]

        r2 = client.get(f"/api/skills/{skill_id}", headers=auth_headers)
        assert r2.status_code == 200
        assert r2.json()["display_name"] == "测试 Skill"

    def test_create_duplicate_name(self, client, auth_headers):
        name = _unique_skill_name()
        payload = {
            "name": name,
            "display_name": "A",
            "definition": "",
        }
        r1 = client.post("/api/skills", json=payload, headers=auth_headers)
        assert r1.status_code == 200

        r2 = client.post("/api/skills", json=payload, headers=auth_headers)
        assert r2.status_code == 400

    def test_create_skill_no_auth(self, client):
        r = client.post(
            "/api/skills",
            json={"name": "noauth", "display_name": "x", "definition": ""},
        )
        assert r.status_code == 401


class TestSkillHubBranches:
    @pytest.fixture()
    def skill_id(self, client, auth_headers):
        name = _unique_skill_name()
        r = client.post(
            "/api/skills",
            json={"name": name, "display_name": "分支测试", "definition": ""},
            headers=auth_headers,
        )
        assert r.status_code == 200
        return r.json()["id"]

    def test_list_branches(self, client, auth_headers, skill_id):
        r = client.get(f"/api/skills/{skill_id}/branches", headers=auth_headers)
        assert r.status_code == 200
        branches = r.json()
        assert len(branches) >= 2
        types = {b["branch_type"] for b in branches}
        assert "master" in types
        assert "standard" in types

    def test_create_personal_branch_idempotent(self, client, auth_headers, eng_headers, skill_id):
        r1 = client.post(f"/api/skills/{skill_id}/branches", headers=eng_headers)
        assert r1.status_code == 200
        branch_id = r1.json()["id"]

        r2 = client.post(f"/api/skills/{skill_id}/branches", headers=eng_headers)
        assert r2.status_code == 200
        assert r2.json()["id"] == branch_id

    def test_get_nonexistent_skill(self, client, auth_headers):
        r = client.get(
            "/api/skills/00000000000000000000000000000000",
            headers=auth_headers,
        )
        assert r.status_code == 404
