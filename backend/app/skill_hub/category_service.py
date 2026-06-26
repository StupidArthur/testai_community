"""
Skill 分类（DB）与 tags 聚合查询。
"""
from __future__ import annotations

import json
import re
from collections import Counter

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.skill_hub.categories import MAX_SKILL_TAGS, MAX_TAG_LENGTH, normalize_tags
from app.skill_hub.models import Skill, SkillCategory, Branch


def list_enabled_categories(db: Session) -> list[SkillCategory]:
    return (
        db.query(SkillCategory)
        .filter(SkillCategory.enabled.is_(True))
        .order_by(SkillCategory.sort_order.asc(), SkillCategory.id.asc())
        .all()
    )


def list_all_categories(db: Session) -> list[SkillCategory]:
    return (
        db.query(SkillCategory)
        .order_by(SkillCategory.sort_order.asc(), SkillCategory.id.asc())
        .all()
    )


def get_category(db: Session, category_id: str) -> SkillCategory | None:
    return db.query(SkillCategory).filter(SkillCategory.id == category_id).first()


def get_category_label(db: Session, category_id: str) -> str:
    row = get_category(db, category_id)
    return row.label if row else category_id


def assert_category_enabled(db: Session, category_id: str) -> str:
    """创建 Skill 时：category 必须存在且 enabled。"""
    cid = (category_id or "").strip()
    row = get_category(db, cid)
    if not row or not row.enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效或未启用的分类：{category_id}，请使用 GET /api/skills/categories",
        )
    return cid


def assert_category_exists(db: Session, category_id: str) -> str:
    """Admin 改 Skill 分类：允许指向已停用分类（保留历史）。"""
    cid = (category_id or "").strip()
    if not get_category(db, cid):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"分类不存在：{category_id}",
        )
    return cid


def validate_category_id_format(category_id: str) -> str:
    """新建分类 id：小写字母、数字、下划线。"""
    cid = (category_id or "").strip()
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,63}", cid):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="分类 id 须以小写字母开头，仅含小写字母、数字、下划线，长度 2~64",
        )
    return cid


def create_category(db: Session, category_id: str, label: str, sort_order: int = 50) -> SkillCategory:
    if get_category(db, category_id):
        raise HTTPException(status_code=400, detail=f"分类 id 已存在：{category_id}")
    row = SkillCategory(id=category_id, label=label.strip(), sort_order=sort_order, enabled=True)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_category(
    db: Session,
    category_id: str,
    *,
    label: str | None = None,
    sort_order: int | None = None,
    enabled: bool | None = None,
) -> SkillCategory:
    row = get_category(db, category_id)
    if not row:
        raise HTTPException(status_code=404, detail="分类不存在")
    if label is not None:
        row.label = label.strip()
    if sort_order is not None:
        row.sort_order = sort_order
    if enabled is not None:
        row.enabled = enabled
    db.commit()
    db.refresh(row)
    return row


def collect_tag_suggestions(db: Session, q: str | None = None, limit: int = 20) -> list[str]:
    """全站已用过的 tags，按出现次数降序；可选关键词过滤。"""
    limit = max(1, min(limit, 50))
    counter: Counter[str] = Counter()
    for raw in db.query(Skill.tags).all():
        tags = _parse_tags_row(raw[0])
        counter.update(tags)
    items = counter.most_common()
    needle = (q or "").strip().lower()
    if needle:
        items = [(t, c) for t, c in items if needle in t.lower()]
    return [t for t, _ in items[:limit]]


def _parse_tags_row(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return normalize_tags([str(x) for x in data])


def get_skill_standard_owner_id(db: Session, skill_id: str) -> int | None:
    """standard 分支 user_id = Skill 创建者（维护 tags 的人）。"""
    owner_id, _ = get_skill_standard_owner(db, skill_id)
    return owner_id


def get_skill_standard_owner(db: Session, skill_id: str) -> tuple[int | None, str | None]:
    """返回 Skill 创建者（standard 分支主人）的 user_id 与 username。"""
    from app.auth.models import User

    row = (
        db.query(Branch.user_id, User.username)
        .join(User, User.id == Branch.user_id)
        .filter(Branch.skill_id == skill_id, Branch.branch_type == "standard")
        .first()
    )
    if not row:
        return None, None
    return row[0], row[1]


def validate_tags_list(tags: list[str] | None) -> list[str]:
    normalized = normalize_tags(tags)
    if len(normalized) > MAX_SKILL_TAGS:
        raise HTTPException(status_code=400, detail=f"标签最多 {MAX_SKILL_TAGS} 个")
    for t in normalized:
        if len(t) > MAX_TAG_LENGTH:
            raise HTTPException(status_code=400, detail=f"单个标签最长 {MAX_TAG_LENGTH} 字符")
    return normalized
