"""skill_hub 启动初始化：默认 Skill 分类目录、revision 回填、平台 Meta-Skill。"""
from __future__ import annotations

from app.platform.database import SessionLocal
from app.skill_hub.categories import DEFAULT_SKILL_CATEGORIES
from app.skill_hub.langgpt_meta_bootstrap import ensure_langgpt_meta_skill
from app.skill_hub.models import SkillCategory, SkillVersion


def ensure_default_categories(_engine=None) -> None:
    """表为空时写入默认分类（幂等）。"""
    db = SessionLocal()
    try:
        if db.query(SkillCategory).count() > 0:
            return
        for cid, label, sort_order in DEFAULT_SKILL_CATEGORIES:
            db.add(
                SkillCategory(
                    id=cid,
                    label=label,
                    sort_order=sort_order,
                    enabled=True,
                )
            )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def ensure_version_revisions(_engine=None) -> None:
    """
    旧库迁移：按 created_at 为每个 Skill 回填 revision（幂等）。
    若 revision 已按 skill 内唯一递增分配则跳过。
    """
    db = SessionLocal()
    try:
        skill_ids = [r[0] for r in db.query(SkillVersion.skill_id).distinct().all()]
        for skill_id in skill_ids:
            versions = (
                db.query(SkillVersion)
                .filter(SkillVersion.skill_id == skill_id)
                .order_by(SkillVersion.created_at.asc(), SkillVersion.version_num.asc())
                .all()
            )
            if not versions:
                continue
            expected = list(range(len(versions)))
            actual = sorted(v.revision for v in versions)
            if actual == expected and len(set(actual)) == len(actual):
                continue
            for idx, v in enumerate(versions):
                v.revision = idx
            db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def ensure_skill_hub_startup(_engine=None) -> None:
    """分类目录 + revision 回填 + LangGPT Meta-Skill（启动幂等）。"""
    ensure_default_categories(_engine)
    ensure_version_revisions(_engine)
    ensure_langgpt_meta_skill(_engine)
