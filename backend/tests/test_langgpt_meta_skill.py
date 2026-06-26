"""LangGPT Meta-Skill 平台权限测试。"""
from __future__ import annotations

from app.skill_hub.langgpt_meta_bootstrap import ensure_langgpt_meta_skill
from app.skill_hub.models import Branch, SkillVersion
from app.skill_hub.platform_skills import LANGGPT_META_SKILL_NAME
from app.skill_hub.service import get_skill_by_name


def _meta_ids():
    ensure_langgpt_meta_skill()
    from app.platform.database import SessionLocal

    db = SessionLocal()
    try:
        skill = get_skill_by_name(db, LANGGPT_META_SKILL_NAME)
        assert skill is not None
        standard = (
            db.query(Branch)
            .filter(Branch.skill_id == skill.id, Branch.branch_type == "standard")
            .first()
        )
        master = (
            db.query(Branch)
            .filter(Branch.skill_id == skill.id, Branch.branch_type == "master")
            .first()
        )
        return skill.id, standard.id, master.id
    finally:
        db.close()


_VERSION_BODY = {
    "role": "x",
    "profile": "",
    "background": "",
    "goals": "",
    "constraints": "",
    "core_skills": "",
    "workflows": "",
    "output_format": "",
    "initialization": "",
    "commit_message": "test",
}


def test_langgpt_meta_fork_forbidden(client, eng_headers):
    skill_id, branch_id, _ = _meta_ids()
    r = client.post(f"/api/skills/{skill_id}/branches/{branch_id}/fork", headers=eng_headers)
    assert r.status_code == 403


def test_langgpt_meta_create_branch_forbidden(client, eng_headers):
    skill_id, _, _ = _meta_ids()
    r = client.post(f"/api/skills/{skill_id}/branches", headers=eng_headers)
    assert r.status_code == 403


def test_langgpt_meta_admin_can_merge(client, auth_headers):
    skill_id, branch_id, _ = _meta_ids()
    from app.platform.database import SessionLocal

    db = SessionLocal()
    try:
        ver = (
            db.query(SkillVersion)
            .filter(SkillVersion.skill_id == skill_id, SkillVersion.branch_id == branch_id)
            .first()
        )
        assert ver is not None
        vid = ver.id
    finally:
        db.close()

    r = client.post(
        f"/api/skills/{skill_id}/merge",
        json={"source_version_id": vid},
        headers=auth_headers,
    )
    assert r.status_code == 200
