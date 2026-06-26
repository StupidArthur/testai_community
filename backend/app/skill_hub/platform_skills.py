"""
平台内置 Skill：日报解析等由系统托管，Skill Hub 中限制分支/编辑/Fork/Merge。
"""
from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.auth.models import User, UserRole
from app.skill_hub.models import Branch, Skill

WORK_DAILY_SKILL_NAME = "Test_Engineer_Daily_Report_Parse"
LANGGPT_META_SKILL_NAME = "LangGPT_Standard_v3"

PLATFORM_LOCKED_SKILL_NAMES: frozenset[str] = frozenset({
    WORK_DAILY_SKILL_NAME,
    LANGGPT_META_SKILL_NAME,
})

# 平台内置 Skill 中允许 Admin merge 到 master 的白名单
PLATFORM_MERGE_ALLOWED_LOCKED: frozenset[str] = frozenset({LANGGPT_META_SKILL_NAME})

_FORBIDDEN_MSG = "平台内置 Skill：仅 Admin 可编辑 standard 分支；禁止创建个人分支与 Fork"
_FORBIDDEN_MERGE_MSG = "该平台内置 Skill 不允许合并到 master"


def is_platform_locked_skill(skill: Skill | str | None) -> bool:
    if skill is None:
        return False
    name = skill if isinstance(skill, str) else skill.name
    return name in PLATFORM_LOCKED_SKILL_NAMES


def is_platform_merge_allowed(skill: Skill | str | None) -> bool:
    if skill is None:
        return False
    name = skill if isinstance(skill, str) else skill.name
    return name in PLATFORM_MERGE_ALLOWED_LOCKED


def assert_platform_merge_allowed(db: Session, skill_id: str) -> None:
    skill = _get_skill(db, skill_id)
    if skill and is_platform_locked_skill(skill) and not is_platform_merge_allowed(skill):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_FORBIDDEN_MERGE_MSG)


def _get_skill(db: Session, skill_id: str) -> Skill | None:
    return db.query(Skill).filter(Skill.id == skill_id).first()


def assert_no_branch_creation_for_platform_skill(db: Session, skill_id: str) -> None:
    """任何人（含 Admin）均不可为平台内置 Skill 创建 personal 等新分支。"""
    skill = _get_skill(db, skill_id)
    if skill and is_platform_locked_skill(skill):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_FORBIDDEN_MSG)


def assert_can_fork_platform_skill(db: Session, skill_id: str) -> None:
    assert_no_branch_creation_for_platform_skill(db, skill_id)


def assert_platform_branch_writable(db: Session, branch: Branch, user: User) -> None:
    """
    平台内置 Skill：仅 Admin 可写 standard；master/personal 及普通用户一律只读。
    非平台 Skill 时不做处理，由通用分支权限逻辑继续判断。
    """
    skill = _get_skill(db, branch.skill_id)
    if not skill or not is_platform_locked_skill(skill):
        return
    if branch.branch_type == "standard" and user.role == UserRole.Admin:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_FORBIDDEN_MSG)
