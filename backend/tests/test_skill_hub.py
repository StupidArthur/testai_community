"""skill_hub 模块 API 测试。"""

import uuid

import pytest


def _unique_skill_name() -> str:
    return f"test_skill_{uuid.uuid4().hex[:8]}"


def _skill_create_payload(name: str | None = None, **extra) -> dict:
    """创建 Skill 请求体（含必选 category）。"""
    payload = {
        "name": name or _unique_skill_name(),
        "display_name": "测试 Skill",
        "definition": "",
        "category": "api_testing",
        "tags": ["pytest"],
    }
    payload.update(extra)
    return payload


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
            json=_skill_create_payload(name=name, display_name="测试 Skill", definition="单元测试用"),
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
        payload = _skill_create_payload(name=name, display_name="A")
        r1 = client.post("/api/skills", json=payload, headers=auth_headers)
        assert r1.status_code == 200

        r2 = client.post("/api/skills", json=payload, headers=auth_headers)
        assert r2.status_code == 400

    def test_create_skill_no_auth(self, client):
        r = client.post(
            "/api/skills",
            json=_skill_create_payload(name="noauth", display_name="x"),
        )
        assert r.status_code == 401

    def test_engineer_create_skill_branch_ownership(self, client, eng_headers):
        """Engineer 可创建；standard 归创建者，master 归 Admin。"""
        name = _unique_skill_name()
        r = client.post(
            "/api/skills",
            json=_skill_create_payload(display_name="工程师创建"),
            headers=eng_headers,
        )
        assert r.status_code == 200
        skill_id = r.json()["id"]

        br = client.get(f"/api/skills/{skill_id}/branches", headers=eng_headers)
        assert br.status_code == 200
        branches = {b["branch_type"]: b for b in br.json()}
        assert branches["standard"]["username"] == "eng_test"
        assert branches["master"]["username"] == "admin"

    def test_creator_cannot_write_master(self, client, eng_headers):
        """创建者也不能直接提交 master 版本。"""
        name = _unique_skill_name()
        r = client.post(
            "/api/skills",
            json=_skill_create_payload(display_name="master 权限"),
            headers=eng_headers,
        )
        skill_id = r.json()["id"]
        master_id = next(
            b["id"]
            for b in client.get(f"/api/skills/{skill_id}/branches", headers=eng_headers).json()
            if b["branch_type"] == "master"
        )
        r2 = client.post(
            f"/api/skills/{skill_id}/branches/{master_id}/versions",
            json={"role": "hack", "commit_message": "x"},
            headers=eng_headers,
        )
        assert r2.status_code == 403


class TestSkillHubBranches:
    @pytest.fixture()
    def skill_id(self, client, auth_headers):
        name = _unique_skill_name()
        r = client.post(
            "/api/skills",
            json=_skill_create_payload(display_name="分支测试"),
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

    def test_creator_can_fork_own_standard_branch(self, client, eng_headers):
        """Skill 创建者可从自己的 standard 分支 Fork 到 personal（复制最新版本）。"""
        r = client.post(
            "/api/skills",
            json=_skill_create_payload(display_name="创建者 Fork"),
            headers=eng_headers,
        )
        assert r.status_code == 200
        skill_id = r.json()["id"]

        branches = client.get(f"/api/skills/{skill_id}/branches", headers=eng_headers).json()
        standard = next(b for b in branches if b["branch_type"] == "standard")
        assert standard["username"] == "eng_test"

        r_fork = client.post(
            f"/api/skills/{skill_id}/branches/{standard['id']}/fork",
            headers=eng_headers,
        )
        assert r_fork.status_code == 200
        body = r_fork.json()
        assert body["branch"]["branch_type"] == "personal"
        assert body["version"]["source_version_id"] is not None

    def test_create_personal_branch_idempotent(self, client, auth_headers, eng_headers, skill_id):
        r1 = client.post(f"/api/skills/{skill_id}/branches", headers=eng_headers)
        assert r1.status_code == 200
        branch_id = r1.json()["id"]

        r2 = client.post(f"/api/skills/{skill_id}/branches", headers=eng_headers)
        assert r2.status_code == 200
        assert r2.json()["id"] == branch_id

        versions = client.get(
            f"/api/skills/{skill_id}/branches/{branch_id}/versions",
            headers=eng_headers,
        ).json()
        assert len(versions) >= 1
        assert versions[0]["source_version_id"] is not None

    def test_get_nonexistent_skill(self, client, auth_headers):
        r = client.get(
            "/api/skills/00000000000000000000000000000000",
            headers=auth_headers,
        )
        assert r.status_code == 404


class TestSkillHubVersions:
    """版本 payload 存取：API 仍暴露九维，DB 仅存 payload。"""

    @pytest.fixture()
    def standard_branch_id(self, client, auth_headers):
        name = _unique_skill_name()
        r = client.post(
            "/api/skills",
            json=_skill_create_payload(display_name="版本测试"),
            headers=auth_headers,
        )
        assert r.status_code == 200
        skill_id = r.json()["id"]
        br = client.get(f"/api/skills/{skill_id}/branches", headers=auth_headers)
        standard = next(b for b in br.json() if b["branch_type"] == "standard")
        return skill_id, standard["id"]

    def test_create_version_roundtrip(self, client, auth_headers, standard_branch_id):
        skill_id, branch_id = standard_branch_id
        payload = {
            "role": "测试专家",
            "profile": "- Author: pytest",
            "background": "背景",
            "goals": "目标",
            "constraints": "必须遵守规则",
            "core_skills": "解析 API",
            "workflows": "1. 第一步",
            "output_format": "Markdown",
            "initialization": "你好",
            "commit_message": "pytest commit",
        }
        r = client.post(
            f"/api/skills/{skill_id}/branches/{branch_id}/versions",
            json=payload,
            headers=auth_headers,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["role"] == "测试专家"
        assert body["core_skills"] == "解析 API"
        assert body["version_num"] >= 1

        r2 = client.get(
            f"/api/skills/{skill_id}/branches/{branch_id}/versions",
            headers=auth_headers,
        )
        assert r2.status_code == 200
        latest = r2.json()[0]
        assert latest["id"] == body["id"]
        assert latest["initialization"] == "你好"


class TestSkillHubCategories:
    def test_list_categories(self, client, auth_headers):
        r = client.get("/api/skills/categories", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert len(body) >= 1
        assert any(c["id"] == "api_testing" for c in body)

    def test_create_invalid_category(self, client, auth_headers):
        r = client.post(
            "/api/skills",
            json=_skill_create_payload(category="not_a_real_category"),
            headers=auth_headers,
        )
        assert r.status_code == 400

    def test_tag_suggestions(self, client, auth_headers):
        client.post(
            "/api/skills",
            json=_skill_create_payload(tags=["openapi", "回归"], category="api_testing"),
            headers=auth_headers,
        )
        r = client.get("/api/skills/tags/suggestions?q=open", headers=auth_headers)
        assert r.status_code == 200
        assert "openapi" in r.json()["tags"]

    def test_admin_manage_categories(self, client, auth_headers):
        r = client.get("/api/skills/categories/manage", headers=auth_headers)
        assert r.status_code == 200
        assert len(r.json()) >= 7

        r2 = client.post(
            "/api/skills/categories",
            json={"id": "custom_cat", "label": "自定义类", "sort_order": 55},
            headers=auth_headers,
        )
        assert r2.status_code == 201
        assert r2.json()["label"] == "自定义类"

        r3 = client.put(
            "/api/skills/categories/custom_cat",
            json={"enabled": False},
            headers=auth_headers,
        )
        assert r3.status_code == 200
        assert r3.json()["enabled"] is False

    def test_list_filter_by_category(self, client, auth_headers):
        r = client.post(
            "/api/skills",
            json=_skill_create_payload(category="security", display_name="安全类"),
            headers=auth_headers,
        )
        assert r.status_code == 200
        r2 = client.get("/api/skills?category=security", headers=auth_headers)
        assert r2.status_code == 200
        assert all(s["category"] == "security" for s in r2.json())
