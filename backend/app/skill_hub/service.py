"""
资产域 service 工具：LLM diff、payload 解析、分支写权限、SkillRef 解析等。
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.ai_service.client import chat
from app.auth.models import User, UserRole
from app.skill_hub.llm_prompts import build_commit_diff_messages
from app.skill_hub.models import Skill, Branch, SkillVersion
from app.skill_hub.platform_skills import assert_platform_branch_writable
from app.skill_hub.skill_ref import SkillRef, ResolvedSkill, ResolveMode
from app.skill_hub.utils import payload_to_dimensions

# version_locator 中 id 前缀长度
VERSION_LOCATOR_ID_PREFIX_LEN = 8

# Skill 调试：用户输入最大长度
MAX_SKILL_DEBUG_INPUT_LENGTH = 16000


def get_skill_by_name(db: Session, name: str) -> Skill | None:
    return db.query(Skill).filter(Skill.name == name).first()


def get_primary_admin_user(db: Session) -> User | None:
    """取平台 Admin（按 id 最早），用于 master 分支归属。"""
    return (
        db.query(User)
        .filter(User.role == UserRole.Admin)
        .order_by(User.id.asc())
        .first()
    )


def assert_can_write_branch(branch: Branch, user: User, db: Session | None = None) -> None:
    """分支写权限：平台内置 Skill 仅 Admin 写 standard；master 仅 Admin；standard/personal 为分支主人或 Admin。"""
    if db is not None:
        assert_platform_branch_writable(db, branch, user)
    if branch.branch_type == "master":
        if user.role != UserRole.Admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="master 分支仅 Admin 可写",
            )
        return
    if branch.user_id != user.id and user.role != UserRole.Admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权修改他人的分支",
        )


def get_skill_version(db: Session, version_id: str) -> SkillVersion | None:
    return db.query(SkillVersion).filter(SkillVersion.id == version_id).first()


def get_skill_version_by_id(db: Session, version_id: str) -> SkillVersion | None:
    """SkillRef pin 解析入口别名。"""
    return get_skill_version(db, version_id)


def get_latest_revision(db: Session, skill_id: str) -> int:
    """Skill 当前最大 revision；无版本时返回 -1。"""
    row = (
        db.query(SkillVersion.revision)
        .filter(SkillVersion.skill_id == skill_id)
        .order_by(SkillVersion.revision.desc())
        .first()
    )
    return row[0] if row else -1


def allocate_version(db: Session, skill_id: str, branch_id: int) -> tuple[int, int]:
    """
    在同一事务内分配分支 version_num 与 Skill 全局 revision。

    Returns:
        (version_num, revision)
    """
    version_num = get_latest_version_num(db, branch_id) + 1
    revision = get_latest_revision(db, skill_id) + 1
    return version_num, revision


def get_branch_head_version(db: Session, branch_id: int) -> SkillVersion | None:
    """取分支 HEAD（version_num 最大）。"""
    return (
        db.query(SkillVersion)
        .filter(SkillVersion.branch_id == branch_id)
        .order_by(SkillVersion.version_num.desc())
        .first()
    )


def get_master_latest_version(db: Session, skill: Skill) -> SkillVersion | None:
    """external_api 发布版：取 master 分支最新版本，而非全 skill 跨分支最高 version_num。"""
    master = (
        db.query(Branch)
        .filter(Branch.skill_id == skill.id, Branch.branch_type == "master")
        .first()
    )
    if not master:
        return None
    return get_branch_head_version(db, master.id)


def get_latest_version_num(db: Session, branch_id: int) -> int:
    """返回该 branch 下当前最大 version_num（无版本则返回 -1，方便 +1 = 0）。"""
    row = (
        db.query(SkillVersion.version_num)
        .filter(SkillVersion.branch_id == branch_id)
        .order_by(SkillVersion.version_num.desc())
        .first()
    )
    return row[0] if row else -1


def _branch_label(branch: Branch, owner_username: str) -> str:
    if branch.branch_type == "personal":
        return f"{owner_username}/personal"
    return branch.branch_type


def build_version_locator(
    skill_name: str,
    branch: Branch,
    owner_username: str,
    version_num: int,
    revision: int,
    version_id: str,
) -> str:
    """人类可读版本定位串。"""
    label = _branch_label(branch, owner_username)
    short_id = version_id[:VERSION_LOCATOR_ID_PREFIX_LEN]
    return f"{skill_name}/{label}@v{version_num} (rev {revision}, id={short_id}…)"


def build_version_locator_for_version(db: Session, v: SkillVersion) -> str:
    """从 ORM 快照构建 version_locator。"""
    skill = db.query(Skill).filter(Skill.id == v.skill_id).first()
    branch = db.query(Branch).filter(Branch.id == v.branch_id).first()
    if not skill or not branch:
        return f"unknown@v{v.version_num} (rev {v.revision})"
    owner = db.query(User).filter(User.id == branch.user_id).first()
    username = owner.username if owner else str(branch.user_id)
    return build_version_locator(
        skill.name, branch, username, v.version_num, v.revision, v.id
    )


def _resolve_branch_for_ref(db: Session, ref: SkillRef, skill: Skill) -> Branch:
    """branch_head 模式下解析目标分支。"""
    if ref.branch_id is not None:
        branch = (
            db.query(Branch)
            .filter(Branch.id == ref.branch_id, Branch.skill_id == skill.id)
            .first()
        )
        if not branch:
            raise HTTPException(status_code=404, detail="Branch 不存在或不属于该 Skill")
        return branch

    branch_type = ref.branch_type or "master"
    q = db.query(Branch).filter(
        Branch.skill_id == skill.id,
        Branch.branch_type == branch_type,
    )
    if branch_type == "personal":
        if ref.owner_user_id is None:
            raise HTTPException(status_code=400, detail="personal 分支需要 owner_user_id")
        q = q.filter(Branch.user_id == ref.owner_user_id)
    branch = q.first()
    if not branch:
        raise HTTPException(status_code=404, detail=f"分支 {branch_type} 不存在")
    return branch


def _to_resolved_skill(
    db: Session,
    v: SkillVersion,
    skill: Skill,
    branch: Branch,
    resolved_at: datetime,
) -> ResolvedSkill:
    owner = db.query(User).filter(User.id == branch.user_id).first()
    username = owner.username if owner else str(branch.user_id)
    return ResolvedSkill(
        skill_id=skill.id,
        skill_name=skill.name,
        version_id=v.id,
        version_num=v.version_num,
        revision=v.revision,
        branch_id=branch.id,
        branch_type=branch.branch_type,
        owner_user_id=branch.user_id,
        owner_username=username,
        version_locator=build_version_locator(
            skill.name, branch, username, v.version_num, v.revision, v.id
        ),
        source_version_id=v.source_version_id,
        payload=v.payload or "",
        fields=version_to_fields(v),
        resolved_at=resolved_at,
    )


def resolve_skill_ref(db: Session, ref: SkillRef) -> ResolvedSkill:
    """
    唯一对外 SkillRef 解析入口。

    pinned：直接读 version_id。
    branch_head：解析分支后取 HEAD。
    """
    resolved_at = datetime.now(timezone.utc)

    if ref.resolve_mode == ResolveMode.pinned:
        v = get_skill_version_by_id(db, ref.version_id)
        if not v:
            raise HTTPException(status_code=404, detail="版本不存在")
        skill = db.query(Skill).filter(Skill.id == v.skill_id).first()
        if not skill:
            raise HTTPException(status_code=404, detail="Skill 不存在")
        if ref.skill_name and skill.name != ref.skill_name:
            raise HTTPException(status_code=400, detail="version_id 与 skill_name 不匹配")
        branch = db.query(Branch).filter(Branch.id == v.branch_id).first()
        if not branch:
            raise HTTPException(status_code=404, detail="Branch 不存在")
        return _to_resolved_skill(db, v, skill, branch, resolved_at)

    # branch_head
    if ref.branch_id is not None:
        branch = db.query(Branch).filter(Branch.id == ref.branch_id).first()
        if not branch:
            raise HTTPException(status_code=404, detail="Branch 不存在")
        skill = db.query(Skill).filter(Skill.id == branch.skill_id).first()
        if not skill:
            raise HTTPException(status_code=404, detail="Skill 不存在")
        if ref.skill_name and skill.name != ref.skill_name:
            raise HTTPException(status_code=400, detail="branch_id 与 skill_name 不匹配")
    else:
        skill = get_skill_by_name(db, ref.skill_name)
        if not skill:
            raise HTTPException(status_code=404, detail="Skill 不存在")
        branch = _resolve_branch_for_ref(db, ref, skill)

    v = get_branch_head_version(db, branch.id)
    if not v:
        raise HTTPException(status_code=404, detail="分支暂无版本")
    return _to_resolved_skill(db, v, skill, branch, resolved_at)


async def run_skill_debug(
    db: Session,
    skill_id: str,
    user_input: str,
    *,
    branch_id: int | None = None,
    version_id: str | None = None,
) -> tuple[ResolvedSkill, str]:
    """
    调试运行 Skill：解析版本 → system=payload → user=user_input → LLM。

    版本定位：version_id（pinned）> branch_id（branch_head）> master HEAD（无则回退 standard）。
    """
    text = (user_input or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="用户输入不能为空")
    if len(text) > MAX_SKILL_DEBUG_INPUT_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"输入过长，最多 {MAX_SKILL_DEBUG_INPUT_LENGTH} 字符",
        )

    skill = db.query(Skill).filter(Skill.id == skill_id).first()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill 不存在")

    if version_id:
        ref = SkillRef(
            resolve_mode=ResolveMode.pinned,
            skill_name=skill.name,
            version_id=version_id,
        )
    elif branch_id is not None:
        branch = (
            db.query(Branch)
            .filter(Branch.id == branch_id, Branch.skill_id == skill_id)
            .first()
        )
        if not branch:
            raise HTTPException(status_code=404, detail="Branch 不存在或不属于该 Skill")
        ref = SkillRef(
            resolve_mode=ResolveMode.branch_head,
            skill_name=skill.name,
            branch_id=branch_id,
        )
    else:
        ref = SkillRef(
            resolve_mode=ResolveMode.branch_head,
            skill_name=skill.name,
            branch_type="master",
        )

    try:
        resolved = resolve_skill_ref(db, ref)
    except HTTPException as exc:
        if (
            exc.status_code == 404
            and ref.resolve_mode == ResolveMode.branch_head
            and (ref.branch_type == "master" or ref.branch_type is None)
            and ref.branch_id is None
        ):
            fallback = SkillRef(
                resolve_mode=ResolveMode.branch_head,
                skill_name=skill.name,
                branch_type="standard",
            )
            resolved = resolve_skill_ref(db, fallback)
        else:
            raise

    messages = [
        {"role": "system", "content": resolved.payload},
        {"role": "user", "content": text},
    ]
    try:
        output = await chat(messages, temperature=0.7, think=False)
    except Exception as exc:
        import logging
        logging.getLogger("app.skill_hub").warning("skill debug LLM failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="LLM 调试调用失败，请检查 MINIMAX_API_KEY 或稍后重试",
        ) from exc

    return resolved, output


def version_to_langgpt_payload(v: SkillVersion) -> str:
    """返回版本快照的 LangGPT 文本（DB 中 payload 为唯一存储）。"""
    return v.payload or ""


def version_to_fields(v: SkillVersion) -> dict[str, str]:
    """从 payload 解析九维字段，供 API 响应与 external_api 使用。"""
    return payload_to_dimensions(v.payload or "")


async def generate_ai_commit_summary(old_version: SkillVersion | None, new_version: SkillVersion) -> str:
    """异步调用 LLM 生成 ai_commit_summary；old_version=None 表示首版。"""
    if old_version is None:
        return "🟢 初始版本：建立了 9 维结构骨架。"
    try:
        old_payload = version_to_langgpt_payload(old_version)
        new_payload = version_to_langgpt_payload(new_version)
        return await chat(
            build_commit_diff_messages(old_payload, new_payload),
            temperature=0.3,
        )
    except Exception:
        return ""  # 失败兜底：留空，不阻塞主流程
