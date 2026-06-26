"""
LangGPT 九维结构化 Meta-Skill 初始化：从项目根 langgpt_standard_v3.md 灌入 SkillHub。
"""
from __future__ import annotations

import logging
from pathlib import Path

from app.auth.models import User, UserRole
from app.platform.database import SessionLocal
from app.skill_hub.models import Branch, Skill, SkillVersion
from app.skill_hub.platform_skills import LANGGPT_META_SKILL_NAME
from app.skill_hub.service import get_primary_admin_user, get_skill_by_name
from app.skill_hub.utils import normalize_langgpt_payload

log = logging.getLogger("app.skill_hub")

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_META_SKILL_MD = _PROJECT_ROOT / "langgpt_standard_v3.md"


def _load_meta_skill_payload() -> str:
    if not _META_SKILL_MD.is_file():
        raise FileNotFoundError(f"缺少 Meta-Skill 源文件: {_META_SKILL_MD}")
    return normalize_langgpt_payload(_META_SKILL_MD.read_text(encoding="utf-8"))


def ensure_langgpt_meta_skill(_engine=None) -> None:
    """幂等：创建 LangGPT 结构化 Meta-Skill（standard + master 各 v0）。"""
    from app.skill_hub.bootstrap import ensure_default_categories

    ensure_default_categories(_engine)
    db = SessionLocal()
    try:
        if get_skill_by_name(db, LANGGPT_META_SKILL_NAME):
            return
        admin = get_primary_admin_user(db) or db.query(User).filter(User.role == UserRole.Admin).first()
        if not admin:
            log.warning("langgpt_meta: 无 Admin，跳过 Skill 创建")
            return

        payload = _load_meta_skill_payload()
        skill = Skill(
            name=LANGGPT_META_SKILL_NAME,
            display_name="LangGPT 九维结构化架构师",
            definition="将零散业务规范或纯文本需求重构为 LangGPT 九维框架提示词（Meta-Skill）。",
            category="documentation",
            tags='["LangGPT", "Meta-Skill", "九维结构化"]',
        )
        db.add(skill)
        db.flush()

        master = Branch(skill_id=skill.id, user_id=admin.id, branch_type="master")
        standard = Branch(skill_id=skill.id, user_id=admin.id, branch_type="standard")
        db.add(master)
        db.add(standard)
        db.flush()

        for i, bid in enumerate((standard.id, master.id)):
            db.add(
                SkillVersion(
                    skill_id=skill.id,
                    branch_id=bid,
                    version_num=0,
                    revision=i,
                    commit_message="initial LangGPT meta skill v0",
                    payload=payload,
                    ai_commit_summary="LangGPT 九维结构化 Meta-Skill 初始版本。",
                )
            )
        db.commit()
        log.info("langgpt_meta: 已创建 Skill %s", LANGGPT_META_SKILL_NAME)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
