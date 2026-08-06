"""项目管理 Pydantic schemas。"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.test_manage.config import (
    ACTION_ENVIRONMENT_MAX_CHARS,
    ACTION_TEST_CONTENT_MAX_CHARS,
    TASK_REQUIREMENT_MAX_CHARS,
    TEXT_FIELD_MAX_CHARS,
)


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    status: str | None = None


class ProjectOut(BaseModel):
    id: str
    name: str
    description: str | None
    status: str
    created_by: int
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class DomainCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    sort_order: int = 0


class DomainOut(BaseModel):
    id: str
    project_id: str
    name: str
    sort_order: int
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class UserBrief(BaseModel):
    id: int
    username: str
    real_name: str = ""


class TaskCreate(BaseModel):
    project_id: str
    domain_id: str
    title: str = Field(..., min_length=1, max_length=300)
    requirement: str = Field(default="", max_length=TASK_REQUIREMENT_MAX_CHARS)
    lead_id: int
    tester_ids: list[int] = Field(default_factory=list)
    publish: bool = False


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    requirement: str | None = Field(default=None, max_length=TASK_REQUIREMENT_MAX_CHARS)
    lead_id: int | None = None
    tester_ids: list[int] | None = None
    status: str | None = None
    change_summary: str = ""  # 发布后更新时的变更说明


class TaskUpdateLogOut(BaseModel):
    id: str
    user_id: int
    summary: str
    detail: str
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class TaskOut(BaseModel):
    id: str
    project_id: str
    domain_id: str
    title: str
    requirement: str
    lead_id: int
    tester_ids: list[int]
    status: str
    created_by: int
    published_at: datetime | None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    project_name: str | None = None
    domain_name: str | None = None
    can_edit: bool = False
    # 进行中时可新建 / 复制本周 Action；已完成为 False
    can_add_action: bool = False

    model_config = {"from_attributes": True}


class TaskDetailOut(TaskOut):
    update_logs: list[TaskUpdateLogOut] = Field(default_factory=list)


class ActionCreate(BaseModel):
    task_id: str
    title: str = Field(..., min_length=1, max_length=300)
    owner_id: int | None = None  # 默认 Task 负责人
    test_content: str = Field(default="", max_length=ACTION_TEST_CONTENT_MAX_CHARS)
    environment: str = Field(default="", max_length=ACTION_ENVIRONMENT_MAX_CHARS)
    source_action_id: str | None = None
    publish: bool = False


class ActionUpdate(BaseModel):
    """仅草稿可改字段；status 仅允许发布/完成（不支持取消）。"""

    title: str | None = Field(default=None, min_length=1, max_length=300)
    owner_id: int | None = None
    test_content: str | None = Field(default=None, max_length=ACTION_TEST_CONTENT_MAX_CHARS)
    environment: str | None = Field(default=None, max_length=ACTION_ENVIRONMENT_MAX_CHARS)
    status: str | None = None


class ActionCloneRequest(BaseModel):
    title: str | None = None
    publish: bool = False


class DailyUpdateUpsert(BaseModel):
    report_date: date | None = None
    progress_percent: int = Field(..., ge=0, le=100)
    risk_blocker: str = Field(default="", max_length=TEXT_FIELD_MAX_CHARS)
    progress_note: str = Field(default="", max_length=TEXT_FIELD_MAX_CHARS)


class DailyUpdateOut(BaseModel):
    id: str
    action_id: str
    user_id: int
    report_date: date
    progress_percent: int
    risk_blocker: str
    progress_note: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class ActionCorrectionCreate(BaseModel):
    note: str = Field(..., min_length=1, max_length=TEXT_FIELD_MAX_CHARS)


class ActionCorrectionOut(BaseModel):
    id: str
    user_id: int
    note: str
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class ActionOut(BaseModel):
    id: str
    task_id: str
    project_id: str
    domain_id: str
    week_start: datetime
    week_key: str
    title: str
    owner_id: int
    test_content: str
    environment: str
    status: str
    source_action_id: str | None
    created_by: int
    published_at: datetime | None
    due_at: datetime | None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    progress_percent: int = 0
    latest_risk: str = ""
    task_title: str | None = None
    project_name: str | None = None
    domain_name: str | None = None
    can_edit_fields: bool = False
    can_change_status: bool = False
    # 进行中且最新日更进度已达完成阈值时可标记完成
    can_mark_done: bool = False
    can_daily: bool = False
    can_correct: bool = False

    model_config = {"from_attributes": True}


class ActionDetailOut(ActionOut):
    daily_updates: list[DailyUpdateOut] = Field(default_factory=list)
    corrections: list[ActionCorrectionOut] = Field(default_factory=list)


class BoardActionOut(ActionOut):
    pass


class BoardTaskOut(BaseModel):
    task: TaskOut
    actions: list[ActionOut]
    week_progress_avg: int = 0
    """展示用进度：手填优先，否则 Action 平均。"""
    progress_is_manual: bool = False
    """False 表示未手填 Task 周进度，当前值为 Action 平均推荐。"""
    recommended_progress: int = 0
    """Action 最新进度算术平均（推荐填写值）。"""
    risks: list[str] = Field(default_factory=list)


class BoardSummaryOut(BaseModel):
    """本周看板页顶汇总。"""

    task_count: int = 0
    action_count: int = 0
    risk_action_count: int = 0
    progress_avg: int = 0
    draft_count: int = 0
    published_count: int = 0
    done_count: int = 0


class BoardOut(BaseModel):
    week_start: datetime
    week_end: datetime
    week_key: str
    weekly_push_at: datetime | None = None
    summary: BoardSummaryOut = Field(default_factory=BoardSummaryOut)
    tasks: list[BoardTaskOut]


class WeekOptionOut(BaseModel):
    """历史周下拉选项（不含本周）。"""

    week_start: datetime
    week_end: datetime
    week_key: str
    label: str


class WeekInfoOut(BaseModel):
    week_start: datetime
    week_end: datetime
    week_key: str
    weekly_push_at: datetime | None = None
    can_set_week_end: bool = False
    history: list[WeekOptionOut] = Field(
        default_factory=list,
        description="最近 N 个历史业务周（不含本周），供「历史」下拉使用",
    )


class WeekEndUpdate(BaseModel):
    """设置当前活动周结束时刻（须晚于现在）。"""

    week_end: datetime


class TaskWeekProgressUpsert(BaseModel):
    progress_percent: int = Field(..., ge=0, le=100)
    note: str = Field(default="", max_length=TEXT_FIELD_MAX_CHARS)


class TaskWeekProgressOut(BaseModel):
    task_id: str
    week_key: str
    progress_percent: int
    recommended_progress: int
    progress_is_manual: bool
    note: str = ""
    updated_by: int | None = None
    updated_at: datetime | None = None
    can_edit: bool = False


class ActionLineageSegmentOut(BaseModel):
    action_id: str
    week_key: str
    week_start: datetime
    title: str
    status: str
    progress_percent: int
    risks: list[str] = Field(default_factory=list)
    is_current: bool = False


class ActionLineageOut(BaseModel):
    action_id: str
    weeks_count: int
    segments: list[ActionLineageSegmentOut] = Field(default_factory=list)


class PushTriggerRequest(BaseModel):
    """手动触发推送。"""

    dry_run: bool = False
    force: bool = False


class PushResultOut(BaseModel):
    kind: str
    period_key: str
    sent: bool
    skipped: bool
    dry_run: bool
    message: str | None = None
    message_bytes: int = 0
    added_count: int = 0
    unresolved_count: int = 0
    resolved_count: int = 0
    reason: str = ""
