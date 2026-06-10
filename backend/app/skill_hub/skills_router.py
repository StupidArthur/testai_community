"""资产域路由（降维重构后）：仅 3 张表 → 极简 REST
  - GET    /api/skills                              列表
  - POST   /api/skills                              创建（自动建 master + standard branch + standard v0）
  - GET    /api/skills/{id}                         详情
  - GET    /api/skills/{id}/branches                列出该 skill 的所有 branch（join user）
  - POST   /api/skills/{id}/branches                当前用户建 personal branch（idempotent）
  - POST   /api/skills/{id}/branches/{bid}/versions 新建版本（异步 LLM diff 后台任务）
  - GET    /api/skills/{id}/branches/{bid}/versions 列出某 branch 的所有版本
  - POST   /api/skills/{id}/merge                   极简 merge：复制 source_version 到 master branch
  - POST   /api/skills/{id}/branches/{bid}/fork     从某 branch 最新版本 fork 到当前用户 personal
"""
from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db, SessionLocal
from app.auth.service import get_current_user
from app.auth.models import User, UserRole
from app.skill_hub.models import Skill, Branch, SkillVersion
from app.skill_hub.schemas import (
    SkillCreate,
    SkillOut,
    BranchOut,
    VersionCreate,
    SkillVersionOut,
    MergeRequest,
    BranchWithUser,
    ForkResponse,
    EvaluateRequest,
    EvaluateResponse,
)
from app.skill_hub.service import (
    get_skill_by_name,
    get_latest_version_num,
    generate_ai_commit_summary,
    version_to_langgpt_payload,
)
from app.skill_hub.minimax_client import call_minimax

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/skills", tags=["skills"])


# ============================================================
# 内部：异步 LLM diff 后台任务
# ============================================================
async def _async_diff_task(version_id: str) -> None:
    db = SessionLocal()
    try:
        v = db.query(SkillVersion).filter(SkillVersion.id == version_id).first()
        if not v:
            return
        prev = (
            db.query(SkillVersion)
            .filter(
                SkillVersion.branch_id == v.branch_id,
                SkillVersion.version_num < v.version_num,
            )
            .order_by(SkillVersion.version_num.desc())
            .first()
        )

        if prev is None:
            v.ai_commit_summary = "初始版本 (Initial Version)"
            db.commit()
            return

        try:
            v.ai_commit_summary = await generate_ai_commit_summary(prev, v)
            db.commit()
        except Exception as e:
            db.rollback()
            error_db = SessionLocal()
            try:
                v2 = error_db.query(SkillVersion).filter(SkillVersion.id == version_id).first()
                if v2:
                    v2.ai_commit_summary = f"生成失败: {e}"
                    error_db.commit()
            except Exception:
                error_db.rollback()
            finally:
                error_db.close()
    except Exception:
        db.rollback()
    finally:
        db.close()


# ============================================================
# Skill 列表 / 详情 / 创建
# ============================================================
@router.get("", response_model=list[SkillOut])
def list_skills(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(Skill).order_by(Skill.created_at.desc()).all()


@router.post("", response_model=SkillOut)
def create_skill(
    data: SkillCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if get_skill_by_name(db, data.name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Skill 名称已存在：{data.name}",
        )

    skill = Skill(name=data.name, display_name=data.display_name, definition=data.definition)
    db.add(skill)
    db.flush()  # 拿到 id

    # 自动建 master + standard 两个 branch
    master_branch = Branch(skill_id=skill.id, user_id=current_user.id, branch_type="master")
    template_branch = Branch(skill_id=skill.id, user_id=current_user.id, branch_type="standard")
    db.add(master_branch)
    db.add(template_branch)
    db.flush()

    # 为 standard 自动生成 v0 初始版本
    initial_version = SkillVersion(
        skill_id=skill.id,
        branch_id=template_branch.id,
        version_num=0,
        commit_message="initial standard v0",
        role="技能助手",
        profile="- Author: System\n- Version: 0.1\n- Language: 中文",
        background="",
        goals="",
        constraints="",
        core_skills="",
        workflows="",
        output_format="",
        initialization="作为提示词助手，你必须遵守上述规则，并使用中文与用户对话。",
        ai_commit_summary="🟢 初始版本：建立了 9 维结构骨架。",
    )
    db.add(initial_version)
    db.commit()
    db.refresh(skill)
    return skill


@router.get("/{skill_id}", response_model=SkillOut)
def get_skill(
    skill_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    skill = db.query(Skill).filter(Skill.id == skill_id).first()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill 不存在")
    return skill


# ============================================================
# Branch 列表 / 创建
# ============================================================

@router.get("/{skill_id}/branches", response_model=list[BranchWithUser])
def list_branches(
    skill_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出该 skill 下所有 Branch（join user 拿 username）。系统级 (master, standard) 置顶。"""
    skill = db.query(Skill).filter(Skill.id == skill_id).first()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill 不存在")

    rows = (
        db.query(Branch, User)
        .join(User, User.id == Branch.user_id)
        .filter(Branch.skill_id == skill_id)
        .all()
    )

    def rank(r):
        b, _ = r
        if b.branch_type == "master":
            return 0
        if b.branch_type == "standard":
            return 1
        return 2

    rows.sort(key=rank)
    return [
        BranchWithUser(
            id=b.id,
            skill_id=b.skill_id,
            user_id=u.id,
            username=u.username,
            branch_type=b.branch_type,
            created_at=b.created_at,
        )
        for b, u in rows
    ]


@router.post("/{skill_id}/branches", response_model=BranchWithUser)
def create_my_branch(
    skill_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """为当前登录用户在该 skill 下建 personal branch（idempotent）。"""
    skill = db.query(Skill).filter(Skill.id == skill_id).first()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill 不存在")

    existing = (
        db.query(Branch)
        .filter(
            Branch.skill_id == skill_id,
            Branch.user_id == current_user.id,
            Branch.branch_type == "personal",
        )
        .first()
    )
    if existing:
        b = existing
    else:
        b = Branch(skill_id=skill_id, user_id=current_user.id, branch_type="personal")
        db.add(b)
        db.commit()
        db.refresh(b)

    return BranchWithUser(
        id=b.id,
        skill_id=b.skill_id,
        user_id=current_user.id,
        username=current_user.username,
        branch_type=b.branch_type,
        created_at=b.created_at,
    )


# ============================================================
# SkillVersion：创建（异步 LLM diff）+ 列表
# ============================================================
@router.get("/{skill_id}/branches/{branch_id}/versions", response_model=list[SkillVersionOut])
def list_branch_versions(
    skill_id: str,
    branch_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (
        db.query(SkillVersion)
        .filter(SkillVersion.skill_id == skill_id, SkillVersion.branch_id == branch_id)
        .order_by(SkillVersion.version_num.desc())
        .all()
    )


@router.post("/{skill_id}/branches/{branch_id}/versions", response_model=SkillVersionOut)
def create_branch_version(
    skill_id: str,
    branch_id: int,
    data: VersionCreate,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """在指定 branch 下新建版本：
       1. 权限校验：仅 branch 主人或 Admin 可写
       2. 计算 version_num = (MAX over this branch) + 1
       3. 9 维数据持久化（ai_commit_summary 留空）
       4. 异步后台任务跑 LLM diff，写回 ai_commit_summary
       5. 主接口立刻返回 200
       6. 并发冲突：IntegrityError → 409
    """
    branch = (
        db.query(Branch)
        .filter(Branch.skill_id == skill_id, Branch.id == branch_id)
        .first()
    )
    if not branch:
        raise HTTPException(status_code=404, detail="Branch 不存在")

    # 权限校验：仅 branch 主人或 Admin 可写
    is_admin = current_user.role == UserRole.Admin
    if branch.user_id != current_user.id and not is_admin:
        raise HTTPException(status_code=403, detail="无权修改他人的分支")

    new_num = get_latest_version_num(db, branch_id) + 1

    for _attempt in range(3):
        sv = SkillVersion(
            skill_id=skill_id,
            branch_id=branch_id,
            version_num=new_num,
            commit_message=data.commit_message or "Update prompt",
            role=data.role,
            profile=data.profile,
            background=data.background,
            goals=data.goals,
            constraints=data.constraints,
            core_skills=data.core_skills,
            workflows=data.workflows,
            output_format=data.output_format,
            initialization=data.initialization,
            ai_commit_summary="",
        )
        db.add(sv)
        try:
            db.commit()
            break
        except IntegrityError:
            db.rollback()
            new_num = get_latest_version_num(db, branch_id) + 1
    else:
        raise HTTPException(status_code=409, detail="版本号冲突，请刷新后重试")
    db.refresh(sv)

    # 注册后台异步任务
    background.add_task(_async_diff_task, sv.id)

    return sv


# ============================================================
# 极简 Merge：复制 source_version 到 master branch
# ============================================================
@router.post("/{skill_id}/merge", response_model=SkillVersionOut)
def merge_to_master(
    skill_id: str,
    data: MergeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """把 source_version 的 9 维数据复制到 master branch，version_num = master MAX + 1。
    仅 Admin 可执行。
    """
    # 权限校验：仅 Admin
    if current_user.role != UserRole.Admin:
        raise HTTPException(status_code=403, detail="仅 Admin 可合并到主干")

    skill = db.query(Skill).filter(Skill.id == skill_id).first()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill 不存在")

    master_branch = (
        db.query(Branch)
        .filter(Branch.skill_id == skill_id, Branch.branch_type == "master")
        .first()
    )
    if not master_branch:
        raise HTTPException(status_code=404, detail="master branch 不存在")

    src = db.query(SkillVersion).filter(SkillVersion.id == data.source_version_id).first()
    if not src:
        raise HTTPException(status_code=404, detail="源版本不存在")

    new_num = get_latest_version_num(db, master_branch.id) + 1

    new_v = SkillVersion(
        skill_id=skill_id,
        branch_id=master_branch.id,
        version_num=new_num,
        commit_message=data.commit_message or f"Merge #{src.version_num} to master",
        role=src.role,
        profile=src.profile,
        background=src.background,
        goals=src.goals,
        constraints=src.constraints,
        core_skills=src.core_skills,
        workflows=src.workflows,
        output_format=src.output_format,
        initialization=src.initialization,
        ai_commit_summary=src.ai_commit_summary,
    )
    db.add(new_v)
    db.commit()
    db.refresh(new_v)
    return new_v


# ============================================================
# Fork：从源 branch 最新版本 fork 到当前用户 personal branch
# 返回 { branch, version }：让前端能精准 navigate 到新建的分支
# ============================================================

@router.post("/{skill_id}/branches/{branch_id}/fork", response_model=ForkResponse)
def fork_branch_to_my_personal(
    skill_id: str,
    branch_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """从源 branch 的最新版本 fork 一份到当前用户的 personal branch（idempotent 建 personal）。
    返回新建/已存在的 branch + 新建的 version 快照，前端用 res.branch.id 直接跳转。
    """
    branch = db.query(Branch).filter(Branch.id == branch_id, Branch.skill_id == skill_id).first()
    if not branch:
        raise HTTPException(status_code=404, detail="源 Branch 不存在")

    src_latest = (
        db.query(SkillVersion)
        .filter(SkillVersion.branch_id == branch_id)
        .order_by(SkillVersion.version_num.desc())
        .first()
    )
    if not src_latest:
        raise HTTPException(status_code=400, detail="源 Branch 暂无版本可 fork")

    # 找或建当前用户的 personal branch
    personal = (
        db.query(Branch)
        .filter(
            Branch.skill_id == skill_id,
            Branch.user_id == current_user.id,
            Branch.branch_type == "personal",
        )
        .first()
    )
    newly_created_branch = False
    if not personal:
        personal = Branch(skill_id=skill_id, user_id=current_user.id, branch_type="personal")
        db.add(personal)
        db.flush()
        newly_created_branch = True

    new_num = get_latest_version_num(db, personal.id) + 1

    new_v = SkillVersion(
        skill_id=skill_id,
        branch_id=personal.id,
        version_num=new_num,
        commit_message=f"forked from branch#{branch_id} (user#{branch.user_id}) v{src_latest.version_num}",
        role=src_latest.role,
        profile=src_latest.profile,
        background=src_latest.background,
        goals=src_latest.goals,
        constraints=src_latest.constraints,
        core_skills=src_latest.core_skills,
        workflows=src_latest.workflows,
        output_format=src_latest.output_format,
        initialization=src_latest.initialization,
        ai_commit_summary="",
    )
    db.add(new_v)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Fork 版本号冲突，请刷新后重试")
    db.refresh(new_v)

    branch_out = BranchWithUser(
        id=personal.id,
        skill_id=personal.skill_id,
        user_id=current_user.id,
        username=current_user.username,
        branch_type=personal.branch_type,
        created_at=personal.created_at,
    )
    return ForkResponse(branch=branch_out, version=new_v)


# ============================================================
# Pre-Commit 评估：草稿 → LLM 评估 + diff + 建议
# ============================================================
from app.skill_hub.utils import fields_to_langgpt

def _draft_to_langgpt(d: EvaluateRequest) -> str:
    return fields_to_langgpt(
        role=d.role,
        profile=d.profile,
        background=d.background,
        goals=d.goals,
        constraints=d.constraints,
        core_skills=d.core_skills,
        workflows=d.workflows,
        output_format=d.output_format,
        initialization=d.initialization,
    )


@router.post(
    "/{skill_id}/branches/{branch_id}/evaluate-draft",
    response_model=EvaluateResponse,
)
async def evaluate_draft(
    skill_id: str,
    branch_id: int,
    data: EvaluateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """提交前预评估：对比当前草稿与该分支最新版本，输出 diff/评估/建议。
    失败时返回 200 + 空字符串（让前端 Modal 显示"跳过审查直接提交"路径）。
    """
    prev = (
        db.query(SkillVersion)
        .filter(SkillVersion.branch_id == branch_id, SkillVersion.skill_id == skill_id)
        .order_by(SkillVersion.version_num.desc())
        .first()
    )

    new_payload = _draft_to_langgpt(data)
    old_payload = version_to_langgpt_payload(prev) if prev else "（首版，无旧版对比）"

    system_prompt = (
        "你是一个 LangGPT Prompt 评审专家。请基于以下 9 维 LangGPT 规范的旧版本与新草稿，"
        "输出三段内容（用中文，Markdown 格式）：\n\n"
        "1. 【diff_summary】用 3-5 个 bullet 简明扼要总结新旧版本在结构与内容上的实质性变化。\n\n"
        "2. 【evaluation】客观评估新草稿的合规性与质量：是否覆盖了 Role/Profile/Background/Goals/"
        "Constraints/Core Skills/Workflows/Output Format/Initialization 这 9 个维度；"
        "Constraints 是否使用强硬祈使句；Workflows 是否为有序 SOP；"
        "Core Skills 是否给出具体实现逻辑而非空泛名字。\n\n"
        "3. 【suggestions】给出 3-5 条具体的可执行改进建议。\n\n"
        "输出格式严格按以下结构（用 --- 分隔三段，不要多余前言）：\n"
        "---\n"
        "【diff_summary】\n<内容>\n"
        "---\n"
        "【evaluation】\n<内容>\n"
        "---\n"
        "【suggestions】\n<内容>\n"
    )
    user_prompt = f"【旧版本】\n{old_payload}\n\n【新草稿】\n{new_payload}"

    try:
        raw = await call_minimax(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
        )
    except Exception as exc:
        log.warning("evaluate_draft LLM call failed: %s", exc)
        return EvaluateResponse(diff_summary="", evaluation="", suggestions="")

    def _extract(tag: str, fallback: str = "") -> str:
        try:
            parts = raw.split(f"【{tag}】")
            if len(parts) < 2:
                return fallback
            after = parts[1]
            seg = after.split("---")[0]
            return seg.strip()
        except Exception:
            return fallback

    return EvaluateResponse(
        diff_summary=_extract("diff_summary"),
        evaluation=_extract("evaluation"),
        suggestions=_extract("suggestions"),
    )
