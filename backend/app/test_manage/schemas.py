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


class SubtaskCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    content: str = Field(default="", max_length=TASK_REQUIREMENT_MAX_CHARS)
    # 开发 / 产品人员（自由文本，多个）
    dev_members: list[str] = Field(default_factory=list)
    pm_members: list[str] = Field(default_factory=list)


class SubtaskUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    content: str | None = Field(default=None, max_length=TASK_REQUIREMENT_MAX_CHARS)
    dev_members: list[str] | None = None
    pm_members: list[str] | None = None


class SubtaskMoveRequest(BaseModel):
    target_task_id: str


class SubtaskOut(BaseModel):
    sid: str
    name: str
    content: str = ""
    dev_members: list[str] = Field(default_factory=list)
    pm_members: list[str] = Field(default_factory=list)


class TaskCreate(BaseModel):
    project_id: str
    domain_id: str
    title: str = Field(..., min_length=1, max_length=300)
    requirement: str = Field(default="", max_length=TASK_REQUIREMENT_MAX_CHARS)
    # 系统需求编号
    sr_code: str = Field(default="", max_length=64)
    # 关联初始需求编号（逗号分隔）
    ir_codes: str = Field(default="", max_length=256)
    # 子类/模块（必填）
    module: str = Field(..., min_length=1, max_length=100)
    req_type: str = Field(default="", max_length=32)
    priority: str = Field(default="", max_length=16)
    change_flag: str = Field(default="", max_length=32)
    acceptance_criteria: str = Field(default="", max_length=4000)
    verifier_id: int | None = None
    verified_at: date | None = None
    verify_result: str = Field(default="", max_length=16)
    remark: str = Field(default="", max_length=4000)
    # 初始子需求明细（建 Task 时一次录入；后续走 subtask 管理接口）
    subtasks: list[SubtaskCreate] = Field(default_factory=list)
    # 开发 / 产品人员（自由文本，多个）
    dev_members: list[str] = Field(default_factory=list)
    pm_members: list[str] = Field(default_factory=list)
    lead_id: int
    publish: bool = False
    req_stage: str | None = None
    expected_handover_at: date | None = None
    actual_handover_at: date | None = None
    test_started_at: date | None = None
    expected_test_end_at: date | None = None
    test_ended_at: date | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    requirement: str | None = Field(default=None, max_length=TASK_REQUIREMENT_MAX_CHARS)
    sr_code: str | None = Field(default=None, max_length=64)
    ir_codes: str | None = Field(default=None, max_length=256)
    module: str | None = Field(default=None, min_length=1, max_length=100)
    req_type: str | None = Field(default=None, max_length=32)
    priority: str | None = Field(default=None, max_length=16)
    change_flag: str | None = Field(default=None, max_length=32)
    acceptance_criteria: str | None = Field(default=None, max_length=4000)
    verifier_id: int | None = None
    verified_at: date | None = None
    verify_result: str | None = Field(default=None, max_length=16)
    remark: str | None = Field(default=None, max_length=4000)
    lead_id: int | None = None
    status: str | None = None  # 测试状态
    change_summary: str = ""  # 发布后更新时的变更说明
    dev_members: list[str] | None = None
    pm_members: list[str] | None = None
    req_stage: str | None = None
    expected_handover_at: date | None = None
    actual_handover_at: date | None = None
    test_started_at: date | None = None
    expected_test_end_at: date | None = None
    test_ended_at: date | None = None


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
    sr_code: str = ""
    ir_codes: str = ""
    module: str = ""
    req_type: str = ""
    priority: str = ""
    change_flag: str = ""
    acceptance_criteria: str = ""
    verifier_id: int | None = None
    verified_at: date | None = None
    verify_result: str = ""
    remark: str = ""
    subtasks: list[SubtaskOut] = Field(default_factory=list)
    dev_members: list[str] = Field(default_factory=list)
    pm_members: list[str] = Field(default_factory=list)
    lead_id: int
    tester_ids: list[int] = Field(default_factory=list)
    status: str
    req_stage: str = "pending_dev"
    expected_handover_at: date | None = None
    actual_handover_at: date | None = None
    test_started_at: date | None = None
    expected_test_end_at: date | None = None
    test_ended_at: date | None = None
    stage_summary: str = ""
    created_by: int
    published_at: datetime | None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    project_name: str | None = None
    domain_name: str | None = None
    can_edit: bool = False
    can_edit_req_stage: bool = False
    # 测试中时可新建 / 复制本周 Action
    can_add_action: bool = False
    # 子需求 / Action 管理入口（宽松模式全员；严格模式 Admin/Manager/Task 负责人）
    can_manage_children: bool = False
    # 合并展示状态（req_stage + status 计算得出）：待开发/开发中/待提测/待测试/测试中-进行中/测试中-已完成/已完成
    display_status: str = ""
    display_status_label: str = ""

    model_config = {"from_attributes": True}


class TaskDetailOut(TaskOut):
    update_logs: list[TaskUpdateLogOut] = Field(default_factory=list)


class ActionCreate(BaseModel):
    task_id: str
    title: str = Field(..., min_length=1, max_length=300)
    # 关联子需求名称（可空 = 未关联；非空时须为该 Task 未删除的 subtask 之一）
    subtask_name: str = Field(default="", max_length=200)
    owner_id: int | None = None  # 默认 Task 负责人
    test_content: str = Field(default="", max_length=ACTION_TEST_CONTENT_MAX_CHARS)
    environment: str = Field(default="", max_length=ACTION_ENVIRONMENT_MAX_CHARS)
    # 开发 / 产品人员（自由文本，多个）
    dev_members: list[str] = Field(default_factory=list)
    pm_members: list[str] = Field(default_factory=list)
    publish: bool = False


class ActionUpdate(BaseModel):
    """仅草稿可改字段；status 仅允许发布/完成（不支持取消）。"""

    title: str | None = Field(default=None, min_length=1, max_length=300)
    # 可空 = 清除关联（未关联）；非空时须为该 Task 未删除的 subtask 之一
    subtask_name: str | None = Field(default=None, max_length=200)
    owner_id: int | None = None
    test_content: str | None = Field(default=None, max_length=ACTION_TEST_CONTENT_MAX_CHARS)
    environment: str | None = Field(default=None, max_length=ACTION_ENVIRONMENT_MAX_CHARS)
    dev_members: list[str] | None = None
    pm_members: list[str] | None = None
    status: str | None = None


class DailyUpdateUpsert(BaseModel):
    report_date: date | None = None
    progress_percent: int = Field(..., ge=0, le=100)
    # 风险说明（UI 文案为「风险」）；是否阻塞单独勾选
    risk_blocker: str = Field(default="", max_length=TEXT_FIELD_MAX_CHARS)
    is_blocking: bool = False
    progress_note: str = Field(default="", max_length=TEXT_FIELD_MAX_CHARS)


class DailyUpdateOut(BaseModel):
    id: str
    action_id: str
    user_id: int
    report_date: date
    progress_percent: int
    risk_blocker: str
    is_blocking: bool = False
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
    subtask_name: str = ""
    owner_id: int
    # 开发 / 产品人员（自由文本，多个）
    dev_members: list[str] = Field(default_factory=list)
    pm_members: list[str] = Field(default_factory=list)
    test_content: str
    environment: str
    status: str
    # 完成时间（仅 done 状态有值）
    completed_at: datetime | None = None
    source_action_id: str | None
    # 周继承带入的起始进度（无日更时的当前进度；周报增量 = 当前 - 起始）
    initial_progress: int = 0
    created_by: int
    published_at: datetime | None
    due_at: datetime | None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    progress_percent: int = 0
    latest_risk: str = ""
    # 最新日更勾选「是否阻塞」；仅阻塞项计入开放阻塞 / 日报
    latest_is_blocking: bool = False
    # 今日是否已提交日更（大屏「今日」筛选用）
    has_daily_today: bool = False
    task_title: str | None = None
    project_name: str | None = None
    domain_name: str | None = None
    can_edit_fields: bool = False
    can_change_status: bool = False
    # 进行中且最新日更进度已达完成阈值时可标记完成
    can_mark_done: bool = False
    can_daily: bool = False
    can_correct: bool = False
    # 负责人更改入口（发布后 Admin/Manager 或 Task 负责人可改派并留痕）
    can_change_owner: bool = False
    # 开发/产品人员编辑入口（宽松模式全员；严格模式 Admin/Manager/Task 负责人）
    can_edit_members: bool = False
    # 关联修正入口（发布后 Admin/Manager 或 Task 负责人可改关联并留痕，可清空为未关联）
    can_relink: bool = False
    # 数据删除入口（宽松模式）：删 Action / 删指定日期日报
    can_delete: bool = False
    can_delete_daily: bool = False

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
    history: list[WeekOptionOut] = Field(
        default_factory=list,
        description="最近 N 个历史业务周（不含本周），供「历史」下拉使用",
    )


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
