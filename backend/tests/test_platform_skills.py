"""平台内置 Skill 权限测试。"""
from __future__ import annotations

from app.daily_report.bootstrap import ensure_work_daily_skill
from app.skill_hub.models import Branch


def _work_daily_ids():
    ensure_work_daily_skill()
    from app.platform.database import SessionLocal
    from app.ai_service.work_daily.constants import WORK_DAILY_SKILL_NAME
    from app.skill_hub.service import get_skill_by_name

    db = SessionLocal()
    try:
        skill = get_skill_by_name(db, WORK_DAILY_SKILL_NAME)
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


def test_platform_locked_fork_forbidden(client, eng_headers):
    skill_id, branch_id, _ = _work_daily_ids()
    r = client.post(f"/api/skills/{skill_id}/branches/{branch_id}/fork", headers=eng_headers)
    assert r.status_code == 403


def test_platform_locked_create_branch_forbidden_admin(client, auth_headers):
    skill_id, _, _ = _work_daily_ids()
    r = client.post(f"/api/skills/{skill_id}/branches", headers=auth_headers)
    assert r.status_code == 403


def test_platform_locked_create_branch_forbidden_engineer(client, eng_headers):
    skill_id, _, _ = _work_daily_ids()
    r = client.post(f"/api/skills/{skill_id}/branches", headers=eng_headers)
    assert r.status_code == 403


def test_platform_locked_master_not_writable_by_admin(client, auth_headers):
    skill_id, _, branch_id = _work_daily_ids()
    r = client.post(
        f"/api/skills/{skill_id}/branches/{branch_id}/versions",
        json=_VERSION_BODY,
        headers=auth_headers,
    )
    assert r.status_code == 403


def test_platform_locked_standard_not_writable_by_engineer(client, eng_headers):
    skill_id, branch_id, _ = _work_daily_ids()
    r = client.post(
        f"/api/skills/{skill_id}/branches/{branch_id}/versions",
        json=_VERSION_BODY,
        headers=eng_headers,
    )
    assert r.status_code == 403


def test_platform_locked_merge_forbidden(client, auth_headers):
    skill_id, branch_id, _ = _work_daily_ids()
    from app.platform.database import SessionLocal
    from app.skill_hub.models import SkillVersion

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
    assert r.status_code == 403
