"""
Pydantic schemas（与 models.py 同步）。
"""
from datetime import datetime
from pydantic import BaseModel, Field


# ============================================================
# Skill
# ============================================================
class SkillCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128, description="代码仓库唯一标识，如 API_Test_Generator")
    display_name: str = Field(..., min_length=1, description="人类可读名，如 API测试用例生成专家")
    definition: str = Field(default="", description="详细定义")


class SkillOut(BaseModel):
    id: str
    name: str
    display_name: str
    definition: str = ""
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


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
# Merge
# ============================================================
class MergeRequest(BaseModel):
    source_version_id: str
    commit_message: str = "Merge to master"
