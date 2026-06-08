"""
资产域 service 工具：LLM diff 等可被路由层 + 后台任务复用的逻辑。
"""
from sqlalchemy.orm import Session

from app.skill_hub.models import Skill, SkillVersion
from app.skill_hub.minimax_client import semantic_diff


def get_skill_by_name(db: Session, name: str) -> Skill | None:
    return db.query(Skill).filter(Skill.name == name).first()


def get_skill_version(db: Session, version_id: str) -> SkillVersion | None:
    return db.query(SkillVersion).filter(SkillVersion.id == version_id).first()


def get_latest_version_num(db: Session, branch_id: int) -> int:
    """返回该 branch 下当前最大 version_num（无版本则返回 -1，方便 +1 = 0）。"""
    row = (
        db.query(SkillVersion.version_num)
        .filter(SkillVersion.branch_id == branch_id)
        .order_by(SkillVersion.version_num.desc())
        .first()
    )
    return row[0] if row else -1


def version_to_langgpt_payload(v: SkillVersion) -> str:
    """把 9 维字段拼成一段 markdown 文本，喂给 LLM 做 diff。"""
    return (
        f"# Role\n{v.role}\n\n"
        f"## Profile\n{v.profile}\n\n"
        f"## Background\n{v.background}\n\n"
        f"## Goals\n{v.goals}\n\n"
        f"## Constraints\n{v.constraints}\n\n"
        f"## Core Skills\n{v.core_skills}\n\n"
        f"## Workflows\n{v.workflows}\n\n"
        f"## Output Format\n{v.output_format}\n\n"
        f"## Initialization\n{v.initialization}\n"
    )


async def generate_ai_commit_summary(old_version: SkillVersion | None, new_version: SkillVersion) -> str:
    """异步调用 LLM 生成 ai_commit_summary；old_version=None 表示首版。"""
    if old_version is None:
        return "🟢 初始版本：建立了 9 维结构骨架。"
    try:
        old_payload = version_to_langgpt_payload(old_version)
        new_payload = version_to_langgpt_payload(new_version)
        return await semantic_diff(old_payload, new_payload)
    except Exception:
        return ""  # 失败兜底：留空，不阻塞主流程
