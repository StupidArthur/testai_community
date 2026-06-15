"""
Pydantic schemas（与 models.py 同步）。

持久层仅存 payload；API 仍暴露九维字段，由 skill_version_to_out 从 payload 解析。
"""
from datetime import datetime
from pydantic import BaseModel, Field, field_validator

from app.skill_hub.models import SkillVersion
from app.skill_hub.utils import payload_to_dimensions
from app.skill_hub.skill_meta import parse_tags_json, tags_to_json
from app.skill_hub.category_service import validate_tags_list


# ============================================================
# Skill
# ============================================================
class SkillCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128, description="代码仓库唯一标识，如 API_Test_Generator")
    display_name: str = Field(..., min_length=1, description="人类可读名，如 API测试用例生成专家")
    definition: str = Field(default="", description="详细定义")
    category: str = Field(..., min_length=1, description="平台分类 id，见 GET /api/skills/categories")
    tags: list[str] = Field(default_factory=list, description="可选自由标签")

    @field_validator("tags")
    @classmethod
    def _tags_ok(cls, v: list[str]) -> list[str]:
        from app.skill_hub.categories import normalize_tags, MAX_SKILL_TAGS, MAX_TAG_LENGTH
        normalized = normalize_tags(v)
        if len(normalized) > MAX_SKILL_TAGS:
            raise ValueError(f"标签最多 {MAX_SKILL_TAGS} 个")
        for t in normalized:
            if len(t) > MAX_TAG_LENGTH:
                raise ValueError(f"单个标签最长 {MAX_TAG_LENGTH} 字符")
        return normalized


class SkillUpdate(BaseModel):
    """PATCH Skill 元数据：category 仅 Admin；tags 为创建者或 Admin。"""
    category: str | None = None
    tags: list[str] | None = None


class SkillCategoryOut(BaseModel):
    id: str
    label: str
    sort_order: int = 0
    enabled: bool = True

    model_config = {"from_attributes": True}


class SkillCategoryCreate(BaseModel):
    id: str = Field(..., min_length=2, max_length=64)
    label: str = Field(..., min_length=1, max_length=128)
    sort_order: int = Field(default=50, ge=0, le=9999)


class SkillCategoryUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=128)
    sort_order: int | None = Field(default=None, ge=0, le=9999)
    enabled: bool | None = None


class TagSuggestionOut(BaseModel):
    tags: list[str]


class SkillOut(BaseModel):
    id: str
    name: str
    display_name: str
    definition: str = ""
    category: str
    category_label: str = ""
    tags: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


def skill_to_out(skill, db) -> SkillOut:
    """ORM → API：补全 category_label 与 tags 列表。"""
    from app.skill_hub.category_service import get_category_label

    return SkillOut(
        id=skill.id,
        name=skill.name,
        display_name=skill.display_name,
        definition=skill.definition or "",
        category=skill.category,
        category_label=get_category_label(db, skill.category),
        tags=parse_tags_json(skill.tags),
        created_at=skill.created_at,
        updated_at=skill.updated_at,
    )


def skill_category_to_out(row) -> SkillCategoryOut:
    return SkillCategoryOut(
        id=row.id,
        label=row.label,
        sort_order=row.sort_order,
        enabled=bool(row.enabled),
    )


# ============================================================
# Branch
# ============================================================
class BranchOut(BaseModel):
    id: int
    skill_id: str
    user_id: int
    branch_type: str  # master / standard / personal
    created_at: datetime

    model_config = {"from_attributes": True}


# ============================================================
# SkillVersion (9 维 Agent 载荷)
# ============================================================
class VersionCreate(BaseModel):
    """创建新版本时填写的 9 维内容"""
    role: str = ""
    profile: str = ""
    background: str = ""
    goals: str = ""
    constraints: str = ""
    core_skills: str = ""
    workflows: str = ""
    output_format: str = ""
    initialization: str = ""
    commit_message: str = "Update prompt"


class SkillVersionOut(BaseModel):
    id: str
    skill_id: str
    branch_id: int
    version_num: int
    revision: int = 0
    source_version_id: str | None = None
    version_locator: str = ""
    commit_message: str
    ai_commit_summary: str = ""
    # 9 维
    role: str = ""
    profile: str = ""
    background: str = ""
    goals: str = ""
    constraints: str = ""
    core_skills: str = ""
    workflows: str = ""
    output_format: str = ""
    initialization: str = ""
    extra_metadata: str = "{}"
    created_at: datetime

    model_config = {"from_attributes": True}


# ============================================================
# SkillRef 解析
# ============================================================
from app.skill_hub.skill_ref import SkillRef, ResolvedSkill  # noqa: E402


class ResolvedSkillOut(ResolvedSkill):
    """HTTP 响应：与 ResolvedSkill 一致。"""


# ============================================================
# Merge
# ============================================================
class MergeRequest(BaseModel):
    source_version_id: str
    commit_message: str = "Merge to master"


# ============================================================
# BranchWithUser (join 查询结果)
# ============================================================
class BranchWithUser(BaseModel):
    id: int
    skill_id: str
    user_id: int
    username: str
    branch_type: str
    created_at: datetime | None

    class Config:
        from_attributes = True


# ============================================================
# Fork
# ============================================================
class ForkResponse(BaseModel):
    branch: BranchWithUser
    version: SkillVersionOut


# ============================================================
# Evaluate Draft
# ============================================================
class EvaluateRequest(BaseModel):
    role: str = ""
    profile: str = ""
    background: str = ""
    goals: str = ""
    constraints: str = ""
    core_skills: str = ""
    workflows: str = ""
    output_format: str = ""
    initialization: str = ""


class EvaluateResponse(BaseModel):
    diff_summary: str = ""
    evaluation: str = ""
    suggestions: str = ""


def skill_version_to_out(v: SkillVersion, db=None) -> SkillVersionOut:
    """ORM → API：从 payload 解析九维，保持前端结构化编辑契约不变。"""
    from sqlalchemy.orm import Session

    dims = payload_to_dimensions(v.payload or "")
    locator = ""
    if db is not None and isinstance(db, Session):
        from app.skill_hub.service import build_version_locator_for_version

        locator = build_version_locator_for_version(db, v)
    return SkillVersionOut(
        id=v.id,
        skill_id=v.skill_id,
        branch_id=v.branch_id,
        version_num=v.version_num,
        revision=v.revision,
        source_version_id=v.source_version_id,
        version_locator=locator,
        commit_message=v.commit_message,
        ai_commit_summary=v.ai_commit_summary or "",
        role=dims["role"],
        profile=dims["profile"],
        background=dims["background"],
        goals=dims["goals"],
        constraints=dims["constraints"],
        core_skills=dims["core_skills"],
        workflows=dims["workflows"],
        output_format=dims["output_format"],
        initialization=dims["initialization"],
        extra_metadata=v.extra_metadata or "{}",
        created_at=v.created_at,
    )
