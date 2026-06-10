"""
降维重构后的资产域模型（Phase 1：彻底重写）。

架构：3 张表 = 3 层物理隔离
  Skill         (顶级代码仓库，UUID 主键)
  Branch        (隔离环境，branch_type ∈ {master, standard, personal})
  SkillVersion  (不可变的数据快照，9 维载荷)

彻底删除：Project / Workspace / PullRequest / SkillStatus / PRStatus
"""
import uuid

from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, func, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.database import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


# ============================================================
# 1. 顶级容器：Skill (代码仓库)
# ============================================================
class Skill(Base):
    __tablename__ = "skills"

    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, unique=True, index=True, nullable=False)        # 如 API_Test_Generator
    display_name = Column(String, nullable=False)                          # 如 API测试用例生成专家
    definition = Column(Text, default="")                                  # 详细定义

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

    # 仅限: 'master' / 'template' / 'personal'
    branch_type = Column(String, default="personal")

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    skill = relationship("Skill", back_populates="branches")
    user = relationship("User")
    versions = relationship("SkillVersion", back_populates="branch", cascade="all, delete-orphan", order_by="SkillVersion.version_num.desc()")


# ============================================================
# 3. 不可变数据载荷：SkillVersion (提交快照，9 维 Agent 设定)
# ============================================================
class SkillVersion(Base):
    __tablename__ = "skill_versions"
    __table_args__ = (
        UniqueConstraint('branch_id', 'version_num', name='uq_branch_version'),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    skill_id = Column(String, ForeignKey("skills.id"), nullable=False)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False)

    # 严格递增的整数版本号: 0, 1, 2...
    version_num = Column(Integer, nullable=False, default=0)
    commit_message = Column(String, default="Update prompt")
    ai_commit_summary = Column(Text, default="")  # 由后台异步任务填充

    # 工业级 Agent 9 大核心载荷 (The 9-Dimensions)
    role = Column(String, default="")             # 1. 角色
    profile = Column(Text, default="")            # 2. 配置档案
    background = Column(Text, default="")         # 3. 背景说明
    goals = Column(Text, default="")              # 4. 核心目标
    constraints = Column(Text, default="")        # 5. 约束与规则 (原 Rules)
    core_skills = Column(Text, default="")        # 6. 核心技能 (强制必填)
    workflows = Column(Text, default="")          # 7. 工作流
    output_format = Column(Text, default="")      # 8. 输出格式
    initialization = Column(Text, default="")     # 9. 初始化/启动语

    extra_metadata = Column(Text, default="{}")   # JSON 兜底扩展

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    skill = relationship("Skill", back_populates="versions")
    branch = relationship("Branch", back_populates="versions")
