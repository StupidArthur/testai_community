"""
降维重构后的资产域模型（Phase 1：彻底重写）。

架构：3 张表 = 3 层物理隔离
  Skill         (顶级代码仓库，UUID 主键)
  Branch        (隔离环境，branch_type ∈ {master, standard, personal})
  SkillVersion  (不可变的数据快照，LangGPT payload 单字段存储九维内容)

彻底删除：Project / Workspace / PullRequest / SkillStatus / PRStatus
"""
import uuid

from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, func, UniqueConstraint, Boolean
from sqlalchemy.orm import relationship

from app.platform.database import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


# ============================================================
# 0. Skill 分类目录（Admin 在 /api/skills/categories 管理）
# ============================================================
class SkillCategory(Base):
    __tablename__ = "skill_categories"

    id = Column(String, primary_key=True)                                   # 如 api_testing
    label = Column(String, nullable=False)                                  # 如 API 测试
    sort_order = Column(Integer, default=50, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ============================================================
# 1. 顶级容器：Skill (代码仓库)
# ============================================================
class Skill(Base):
    __tablename__ = "skills"

    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, unique=True, index=True, nullable=False)        # 如 API_Test_Generator
    display_name = Column(String, nullable=False)                          # 如 API测试用例生成专家
    definition = Column(Text, default="")                                  # 详细定义
    category = Column(String, index=True, nullable=False, default="other")  # 平台分类，见 categories.py
    tags = Column(Text, default="[]")                                      # JSON 字符串数组，自由标签

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    branches = relationship("Branch", back_populates="skill", cascade="all, delete-orphan")
    versions = relationship("SkillVersion", back_populates="skill", cascade="all, delete-orphan", order_by="SkillVersion.version_num.desc()")


# ============================================================
# 2. 隔离环境：Branch (分支)
# ============================================================
class Branch(Base):
    __tablename__ = "branches"
    __table_args__ = (
        UniqueConstraint('skill_id', 'user_id', 'branch_type', name='uq_skill_user_branch'),
    )

    id = Column(Integer, primary_key=True, index=True)
    skill_id = Column(String, ForeignKey("skills.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # 仅限: 'master' / 'standard' / 'personal'
    branch_type = Column(String, default="personal")

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    skill = relationship("Skill", back_populates="branches")
    user = relationship("User")
    versions = relationship("SkillVersion", back_populates="branch", cascade="all, delete-orphan", order_by="SkillVersion.version_num.desc()")


# ============================================================
# 3. 不可变数据载荷：SkillVersion (LangGPT Markdown 快照)
# ============================================================
class SkillVersion(Base):
    __tablename__ = "skill_versions"
    __table_args__ = (
        UniqueConstraint('branch_id', 'version_num', name='uq_branch_version'),
        UniqueConstraint('skill_id', 'revision', name='uq_skill_revision'),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    skill_id = Column(String, ForeignKey("skills.id"), nullable=False)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False)

    # 分支内严格递增: 0, 1, 2...
    version_num = Column(Integer, nullable=False, default=0)
    # Skill 级全局单调递增序号（跨分支审计排序）
    revision = Column(Integer, nullable=False, default=0)
    # Merge / Fork 溯源：指向源快照 id
    source_version_id = Column(String, ForeignKey("skill_versions.id"), nullable=True)

    commit_message = Column(String, default="Update prompt")
    ai_commit_summary = Column(Text, default="")  # 由后台异步任务填充

    # 九维 LangGPT 内容的唯一持久化字段（# Role / ## Profile / ...）
    payload = Column(Text, default="")

    extra_metadata = Column(Text, default="{}")   # JSON 兜底扩展

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    skill = relationship("Skill", back_populates="versions")
    branch = relationship("Branch", back_populates="versions")
    source_version = relationship(
        "SkillVersion",
        remote_side="SkillVersion.id",
        foreign_keys=[source_version_id],
    )
