"""
项目管理 ORM：Project → Domain → Task → Action。
"""
from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship

from app.platform.database import Base
from app.test_manage.config import (
    PROJECT_STATUS_ACTIVE,
    REQ_STAGE_DEFAULT,
    STATUS_DRAFT,
    TASK_STATUS_DRAFT,
)


def _new_uuid() -> str:
    return str(uuid.uuid4())


class TmProject(Base):
    """项目容器（创建/组织维度，如 TPT V2.1）。"""

    __tablename__ = "tm_projects"

    id = Column(String, primary_key=True, default=_new_uuid)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String, nullable=False, default=PROJECT_STATUS_ACTIVE, index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    domains = relationship(
        "TmDomain", back_populates="project", cascade="all, delete-orphan"
    )


class TmDomain(Base):
    """领域：平台 / Agent / 交付 / 定制…"""

    __tablename__ = "tm_domains"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_tm_domain_project_name"),
    )

    id = Column(String, primary_key=True, default=_new_uuid)
    project_id = Column(
        String, ForeignKey("tm_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name = Column(String, nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    project = relationship("TmProject", back_populates="domains")
    tasks = relationship("TmTask", back_populates="domain", cascade="all, delete-orphan")


class TmTask(Base):
    """主题任务：需求内容 + 测试负责人 + 测试人员 + 需求进展。"""

    __tablename__ = "tm_tasks"

    id = Column(String, primary_key=True, default=_new_uuid)
    project_id = Column(String, ForeignKey("tm_projects.id"), nullable=False, index=True)
    domain_id = Column(
        String, ForeignKey("tm_domains.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title = Column(String, nullable=False)
    requirement = Column(Text, nullable=False, default="")
    lead_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    status = Column(String, nullable=False, default=TASK_STATUS_DRAFT, index=True)
    # 需求进展（整需求生命周期）；测试状态见 status
    req_stage = Column(String, nullable=False, default=REQ_STAGE_DEFAULT, index=True)
    expected_handover_at = Column(Date, nullable=True)  # 待提测：预计提测
    actual_handover_at = Column(Date, nullable=True)  # 待测试：实际提测
    test_started_at = Column(Date, nullable=True)  # 测试中：开始
    expected_test_end_at = Column(Date, nullable=True)  # 测试中：预计结束
    test_ended_at = Column(Date, nullable=True)  # 测试完成：实际结束
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    published_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    domain = relationship("TmDomain", back_populates="tasks")
    testers = relationship(
        "TmTaskTester", back_populates="task", cascade="all, delete-orphan"
    )
    update_logs = relationship(
        "TmTaskUpdateLog",
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="TmTaskUpdateLog.created_at.desc()",
    )
    actions = relationship("TmAction", back_populates="task", cascade="all, delete-orphan")


class TmTaskTester(Base):
    """Task 测试人员（不含负责人）。"""

    __tablename__ = "tm_task_testers"
    __table_args__ = (UniqueConstraint("task_id", "user_id", name="uq_tm_task_tester"),)

    id = Column(String, primary_key=True, default=_new_uuid)
    task_id = Column(
        String, ForeignKey("tm_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    task = relationship("TmTask", back_populates="testers")


class TmTaskUpdateLog(Base):
    """Task 发布后更新历史。"""

    __tablename__ = "tm_task_update_logs"

    id = Column(String, primary_key=True, default=_new_uuid)
    task_id = Column(
        String, ForeignKey("tm_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    summary = Column(String, nullable=False, default="")
    detail = Column(Text, nullable=False, default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    task = relationship("TmTask", back_populates="update_logs")


class TmAction(Base):
    """周 Action：测试内容 / 环境；草稿可改，发布后字段锁定。"""

    __tablename__ = "tm_actions"

    id = Column(String, primary_key=True, default=_new_uuid)
    task_id = Column(
        String, ForeignKey("tm_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id = Column(String, ForeignKey("tm_projects.id"), nullable=False, index=True)
    domain_id = Column(String, ForeignKey("tm_domains.id"), nullable=False, index=True)
    week_start = Column(DateTime(timezone=True), nullable=False, index=True)
    week_key = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    test_content = Column(Text, nullable=False, default="")
    environment = Column(Text, nullable=False, default="")
    status = Column(String, nullable=False, default=STATUS_DRAFT, index=True)
    source_action_id = Column(String, ForeignKey("tm_actions.id"), nullable=True, index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    published_at = Column(DateTime(timezone=True), nullable=True)
    due_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    task = relationship("TmTask", back_populates="actions")
    daily_updates = relationship(
        "TmDailyUpdate", back_populates="action", cascade="all, delete-orphan"
    )
    corrections = relationship(
        "TmActionCorrection",
        back_populates="action",
        cascade="all, delete-orphan",
        order_by="TmActionCorrection.created_at.desc()",
    )


class TmActionCorrection(Base):
    """发布后字段锁定；更正说明仅追加（含周三截止后纠错）。"""

    __tablename__ = "tm_action_corrections"

    id = Column(String, primary_key=True, default=_new_uuid)
    action_id = Column(
        String, ForeignKey("tm_actions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    note = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    action = relationship("TmAction", back_populates="corrections")


class TmDailyUpdate(Base):
    """每日进度；每个 Action 每个自然日仅一条，谁写谁覆盖（负责人/管理员）。"""

    __tablename__ = "tm_daily_updates"
    __table_args__ = (
        UniqueConstraint(
            "action_id", "report_date", name="uq_tm_daily_update_action_day"
        ),
    )

    id = Column(String, primary_key=True, default=_new_uuid)
    action_id = Column(
        String, ForeignKey("tm_actions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    report_date = Column(Date, nullable=False)
    progress_percent = Column(Integer, nullable=False, default=0)
    # 风险说明（原阻塞文案字段名保留）；是否阻塞由 is_blocking 单独标记
    risk_blocker = Column(Text, nullable=False, default="")
    is_blocking = Column(Boolean, nullable=False, default=False)
    progress_note = Column(Text, nullable=False, default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    action = relationship("TmAction", back_populates="daily_updates")


class TmPushSnapshot(Base):
    """
    上次推送时的「开放风险」快照（按日报/周报各保留一行最新）。

    open_risks_json: {action_id: {risk, task_title, action_title, owner_name, domain_name, progress}}
    """

    __tablename__ = "tm_push_snapshots"

    id = Column(String, primary_key=True, default=_new_uuid)
    report_kind = Column(String, nullable=False, unique=True, index=True)
    open_risks_json = Column(Text, nullable=False, default="{}")
    last_period_key = Column(String, nullable=True)
    last_message = Column(Text, nullable=True)
    last_trigger = Column(String, nullable=True)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TmPushRun(Base):
    """推送成功记录：用于定时任务按日/周幂等（同一 period 不重复发）。"""

    __tablename__ = "tm_push_runs"
    __table_args__ = (
        UniqueConstraint("report_kind", "period_key", name="uq_tm_push_run_period"),
    )

    id = Column(String, primary_key=True, default=_new_uuid)
    report_kind = Column(String, nullable=False, index=True)
    period_key = Column(String, nullable=False, index=True)
    trigger = Column(String, nullable=False, default="schedule")
    skipped = Column(Integer, nullable=False, default=0)  # 1=无内容跳过
    message_bytes = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class TmWeekPeriod(Base):
    """
    业务周窗口：Admin/Manager 可配置本周结束时刻；起点为上一窗口终点。
    默认仍按「周三 17:00 起、+7 天」自动开窗。
    """

    __tablename__ = "tm_week_periods"

    id = Column(String, primary_key=True, default=_new_uuid)
    week_key = Column(String, nullable=False, unique=True, index=True)
    week_start = Column(DateTime(timezone=True), nullable=False, index=True)
    week_end = Column(DateTime(timezone=True), nullable=False, index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TmTaskWeekProgress(Base):
    """
    Task 本周进度（周结束前由 Admin/Manager/测试负责人手填）。
    未填写时展示侧用 Action 平均，并标记未手填。
    """

    __tablename__ = "tm_task_week_progress"
    __table_args__ = (
        UniqueConstraint("task_id", "week_key", name="uq_tm_task_week_progress"),
    )

    id = Column(String, primary_key=True, default=_new_uuid)
    task_id = Column(
        String, ForeignKey("tm_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    week_key = Column(String, nullable=False, index=True)
    progress_percent = Column(Integer, nullable=False, default=0)
    note = Column(Text, nullable=False, default="")
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TmTaskStageSnapshot(Base):
    """
    历史周需求进展快照：切周时固化，历史大屏读快照而非当前阶段。
    """

    __tablename__ = "tm_task_stage_snapshots"
    __table_args__ = (
        UniqueConstraint("task_id", "week_key", name="uq_tm_task_stage_snapshot"),
    )

    id = Column(String, primary_key=True, default=_new_uuid)
    task_id = Column(
        String, ForeignKey("tm_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    week_key = Column(String, nullable=False, index=True)
    req_stage = Column(String, nullable=False, default=REQ_STAGE_DEFAULT, index=True)
    expected_handover_at = Column(Date, nullable=True)
    actual_handover_at = Column(Date, nullable=True)
    test_started_at = Column(Date, nullable=True)
    expected_test_end_at = Column(Date, nullable=True)
    test_ended_at = Column(Date, nullable=True)
    captured_at = Column(DateTime(timezone=True), server_default=func.now())
