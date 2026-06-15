"""SkillRef 解析单元与集成测试。"""

import uuid

import pytest

from app.skill_hub.skill_ref import SkillRef, ResolveMode


def _unique_skill_name() -> str:
    return f"ref_skill_{uuid.uuid4().hex[:8]}"


def _skill_create_payload(name: str | None = None, **extra) -> dict:
    payload = {
        "name": name or _unique_skill_name(),
        "display_name": "SkillRef 测试",
        "definition": "",
        "category": "api_testing",
        "tags": [],
    }
    payload.update(extra)
    return payload


@pytest.fixture()
def skill_ctx(client, auth_headers):
    """创建 Skill，返回 skill_id, name, branches dict。"""
    name = _unique_skill_name()
    r = client.post(
        "/api/skills",
        json=_skill_create_payload(name=name),
        headers=auth_headers,
    )
    assert r.status_code == 200
    skill_id = r.json()["id"]
    br = client.get(f"/api/skills/{skill_id}/branches", headers=auth_headers).json()
    branches = {b["branch_type"]: b for b in br}
    return {"skill_id": skill_id, "name": name, "branches": branches, "headers": auth_headers}


def _commit_version(client, skill_id, branch_id, headers, role_suffix=""):
    payload = {
        "role": f"测试角色{role_suffix}",
        "profile": "- Author: pytest",
        "background": "背景",
        "goals": "目标",
        "constraints": "必须遵守",
        "core_skills": "技能",
        "workflows": "1. 步骤",
        "output_format": "md",
        "initialization": "你好",
        "commit_message": f"commit{role_suffix}",
    }
    r = client.post(
        f"/api/skills/{skill_id}/branches/{branch_id}/versions",
        json=payload,
        headers=headers,
    )
    assert r.status_code == 200
    return r.json()


class TestSkillRefResolveApi:
    def test_branch_head_master(self, client, skill_ctx):
        ref = SkillRef(
            resolve_mode=ResolveMode.branch_head,
            skill_name=skill_ctx["name"],
            branch_type="standard",
        )
        r = client.post("/api/skills/resolve", json=ref.model_dump(), headers=skill_ctx["headers"])
        assert r.status_code == 200
        body = r.json()
        assert body["skill_name"] == skill_ctx["name"]
        assert body["branch_type"] == "standard"
        assert "version_locator" in body
        assert body["revision"] >= 0

    def test_pinned_version(self, client, skill_ctx):
        std_id = skill_ctx["branches"]["standard"]["id"]
        v1 = _commit_version(client, skill_ctx["skill_id"], std_id, skill_ctx["headers"], "1")
        ref = SkillRef(resolve_mode=ResolveMode.pinned, version_id=v1["id"])
        r = client.post("/api/skills/resolve", json=ref.model_dump(), headers=skill_ctx["headers"])
        assert r.status_code == 200
        assert r.json()["version_id"] == v1["id"]
        assert r.json()["version_num"] == v1["version_num"]

    def test_pinned_wrong_skill_name(self, client, skill_ctx):
        std_id = skill_ctx["branches"]["standard"]["id"]
        v1 = _commit_version(client, skill_ctx["skill_id"], std_id, skill_ctx["headers"])
        ref = SkillRef(
            resolve_mode=ResolveMode.pinned,
            version_id=v1["id"],
            skill_name="Wrong_Name",
        )
        r = client.post("/api/skills/resolve", json=ref.model_dump(), headers=skill_ctx["headers"])
        assert r.status_code == 400

    def test_branch_no_versions_404(self, client, skill_ctx):
        ref = SkillRef(
            resolve_mode=ResolveMode.branch_head,
            skill_name=skill_ctx["name"],
            branch_type="master",
        )
        r = client.post("/api/skills/resolve", json=ref.model_dump(), headers=skill_ctx["headers"])
        assert r.status_code == 404

    def test_personal_branch_head(self, client, skill_ctx, eng_headers):
        eng_branch = client.post(
            f"/api/skills/{skill_ctx['skill_id']}/branches",
            headers=eng_headers,
        ).json()
        v = _commit_version(
            client, skill_ctx["skill_id"], eng_branch["id"], eng_headers, "p"
        )
        ref = SkillRef(
            resolve_mode=ResolveMode.branch_head,
            skill_name=skill_ctx["name"],
            branch_id=eng_branch["id"],
        )
        r = client.post("/api/skills/resolve", json=ref.model_dump(), headers=skill_ctx["headers"])
        assert r.status_code == 200
        assert r.json()["version_id"] == v["id"]


class TestRevisionAndProvenance:
    def test_revision_increments_across_branches(self, client, skill_ctx, eng_headers):
        std_id = skill_ctx["branches"]["standard"]["id"]
        v_std = _commit_version(client, skill_ctx["skill_id"], std_id, skill_ctx["headers"], "a")
        eng_branch = client.post(
            f"/api/skills/{skill_ctx['skill_id']}/branches",
            headers=eng_headers,
        ).json()
        v_eng = _commit_version(
            client, skill_ctx["skill_id"], eng_branch["id"], eng_headers, "b"
        )
        assert v_eng["revision"] > v_std["revision"]

    def test_merge_sets_source_version_id(self, client, skill_ctx, auth_headers):
        std_id = skill_ctx["branches"]["standard"]["id"]
        v = _commit_version(client, skill_ctx["skill_id"], std_id, auth_headers, "merge")
        master_id = skill_ctx["branches"]["master"]["id"]
        # master 需先有 v0 才能 merge 后 version_num 有意义；先 commit master
        _commit_version(client, skill_ctx["skill_id"], master_id, auth_headers, "m0")
        r = client.post(
            f"/api/skills/{skill_ctx['skill_id']}/merge",
            json={"source_version_id": v["id"], "commit_message": "merge test"},
            headers=auth_headers,
        )
        assert r.status_code == 200
        merged = r.json()
        assert merged["source_version_id"] == v["id"]
        assert "rev" in merged["version_locator"] or merged["revision"] >= 0

    def test_fork_sets_source_version_id(self, client, skill_ctx, eng_headers):
        std_id = skill_ctx["branches"]["standard"]["id"]
        r = client.post(
            f"/api/skills/{skill_ctx['skill_id']}/branches/{std_id}/fork",
            headers=eng_headers,
        )
        assert r.status_code == 200
        forked = r.json()["version"]
        assert forked["source_version_id"] is not None


class TestSkillRefFloatDrift:
    def test_branch_head_changes_after_new_commit(self, client, skill_ctx):
        std_id = skill_ctx["branches"]["standard"]["id"]
        ref = SkillRef(
            resolve_mode=ResolveMode.branch_head,
            skill_name=skill_ctx["name"],
            branch_type="standard",
        )
        r1 = client.post("/api/skills/resolve", json=ref.model_dump(), headers=skill_ctx["headers"])
        vid1 = r1.json()["version_id"]
        _commit_version(client, skill_ctx["skill_id"], std_id, skill_ctx["headers"], "new")
        r2 = client.post("/api/skills/resolve", json=ref.model_dump(), headers=skill_ctx["headers"])
        vid2 = r2.json()["version_id"]
        assert vid2 != vid1

    def test_pinned_stable_after_new_commit(self, client, skill_ctx):
        std_id = skill_ctx["branches"]["standard"]["id"]
        v = _commit_version(client, skill_ctx["skill_id"], std_id, skill_ctx["headers"], "pin")
        ref = SkillRef(resolve_mode=ResolveMode.pinned, version_id=v["id"])
        r1 = client.post("/api/skills/resolve", json=ref.model_dump(), headers=skill_ctx["headers"])
        _commit_version(client, skill_ctx["skill_id"], std_id, skill_ctx["headers"], "after")
        r2 = client.post("/api/skills/resolve", json=ref.model_dump(), headers=skill_ctx["headers"])
        assert r1.json()["version_id"] == r2.json()["version_id"]
