"""SkillRef：跨模块引用 Skill 版本的统一数据结构。"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ResolveMode(str, Enum):
    """引用解析模式。"""

    pinned = "pinned"
    branch_head = "branch_head"


class SkillRef(BaseModel):
    """
    业务模块存储的 Skill 引用描述（JSON 可序列化）。

    pinned：精确锁定 version_id。
    branch_head：浮动到分支 HEAD（需 skill_name + 分支定位）。
    """

    resolve_mode: ResolveMode = ResolveMode.branch_head
    skill_name: str | None = Field(default=None, description="Skill 仓库名，branch_head 必填")
    version_id: str | None = Field(default=None, description="pinned 模式必填")
    branch_id: int | None = Field(default=None, description="branch_head 最精确分支定位")
    branch_type: Literal["master", "standard", "personal"] | None = Field(
        default=None,
        description="branch_head 分支类型；默认 master",
    )
    owner_user_id: int | None = Field(
        default=None,
        description="personal 分支时指定 owner（无 branch_id 时必填）",
    )

    @model_validator(mode="after")
    def _validate_ref(self) -> SkillRef:
        if self.resolve_mode == ResolveMode.pinned:
            if not self.version_id:
                raise ValueError("pinned 模式需要 version_id")
            return self

        if not self.skill_name and self.branch_id is None:
            raise ValueError("branch_head 需要 skill_name 或 branch_id")
        if self.branch_type == "personal" and self.branch_id is None and self.owner_user_id is None:
            raise ValueError("personal 分支需要 branch_id 或 owner_user_id")
        return self


class ResolvedSkill(BaseModel):
    """resolve_skill_ref 解析结果：不可变快照 + 元数据。"""

    skill_id: str
    skill_name: str
    version_id: str
    version_num: int
    revision: int
    branch_id: int
    branch_type: str
    owner_user_id: int
    owner_username: str = ""
    version_locator: str
    source_version_id: str | None = None
    payload: str
    fields: dict[str, str]
    resolved_at: datetime
