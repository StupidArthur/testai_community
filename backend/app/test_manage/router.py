"""项目管理 HTTP：/api/test-manage"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.models import User
from app.auth.service import get_current_user, RequireRole
from app.platform.database import get_db
from app.test_manage import service as svc
from app.test_manage import push_service as push_svc
from app.test_manage.config import PUSH_TRIGGER_MANUAL
from app.test_manage.schemas import (
    ActionCloneRequest,
    ActionCorrectionCreate,
    ActionCorrectionOut,
    ActionCreate,
    ActionDetailOut,
    ActionLineageOut,
    ActionOut,
    ActionUpdate,
    BoardOut,
    DailyUpdateOut,
    DailyUpdateUpsert,
    DomainCreate,
    DomainOut,
    ProjectCreate,
    ProjectOut,
    ProjectUpdate,
    PushResultOut,
    PushTriggerRequest,
    TaskCreate,
    TaskDetailOut,
    TaskOut,
    TaskUpdate,
    TaskWeekProgressOut,
    TaskWeekProgressUpsert,
    UserBrief,
    WeekEndUpdate,
    WeekInfoOut,
)

router = APIRouter(prefix="/api/test-manage", tags=["test_manage"])


@router.get("/week", response_model=WeekInfoOut)
def api_week(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.get_week_info(db, current_user)


@router.put("/week/end", response_model=WeekInfoOut)
def api_set_week_end(
    data: WeekEndUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Admin/Manager：设置当前活动周结束时刻（并同步本周 Action.due_at）。"""
    return svc.update_week_end(db, current_user, data)


@router.get("/users", response_model=list[UserBrief])
def api_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.list_assignable_users(db, current_user)


@router.get("/board", response_model=BoardOut)
def api_board(
    week_start: datetime | None = None,
    project_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """周 × Task 看板（项目管理首页）。"""
    return svc.get_board(
        db, current_user, week_start=week_start, project_id=project_id
    )


@router.get("/projects", response_model=list[ProjectOut])
def api_list_projects(
    include_archived: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ = current_user
    return svc.list_projects(db, include_archived=include_archived)


@router.post("/projects", response_model=ProjectOut, status_code=201)
def api_create_project(
    data: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.create_project(db, current_user, data)


@router.patch("/projects/{project_id}", response_model=ProjectOut)
def api_update_project(
    project_id: str,
    data: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.update_project(db, current_user, project_id, data)


@router.get("/projects/{project_id}/domains", response_model=list[DomainOut])
def api_list_domains(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ = current_user
    return svc.list_domains(db, project_id)


@router.post("/projects/{project_id}/domains", response_model=DomainOut, status_code=201)
def api_create_domain(
    project_id: str,
    data: DomainCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.create_domain(db, current_user, project_id, data)


@router.get("/tasks", response_model=list[TaskOut])
def api_list_tasks(
    project_id: str | None = None,
    domain_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.list_tasks(
        db, current_user, project_id=project_id, domain_id=domain_id
    )


@router.post("/tasks", response_model=TaskOut, status_code=201)
def api_create_task(
    data: TaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.create_task(db, current_user, data)


@router.get("/tasks/{task_id}", response_model=TaskDetailOut)
def api_get_task(
    task_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.get_task(db, current_user, task_id)


@router.get("/tasks/{task_id}/week-progress", response_model=TaskWeekProgressOut)
def api_get_task_week_progress(
    task_id: str,
    week_key: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.get_task_week_progress(db, current_user, task_id, week_key_s=week_key)


@router.put("/tasks/{task_id}/week-progress", response_model=TaskWeekProgressOut)
def api_put_task_week_progress(
    task_id: str,
    data: TaskWeekProgressUpsert,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """周结束前填写 Task 进度（推荐值=本周 Action 平均）。"""
    return svc.upsert_task_week_progress(db, current_user, task_id, data)


@router.patch("/tasks/{task_id}", response_model=TaskOut)
def api_update_task(
    task_id: str,
    data: TaskUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.update_task(db, current_user, task_id, data)


@router.get("/actions/mine", response_model=list[ActionOut])
def api_mine(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.list_mine_actions(db, current_user)


@router.get("/tasks/{task_id}/clone-candidates", response_model=list[ActionOut])
def api_clone_candidates(
    task_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.list_clone_candidates(db, current_user, task_id)


@router.post("/actions", response_model=ActionOut, status_code=201)
def api_create_action(
    data: ActionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.create_action(db, current_user, data)


@router.post("/actions/{action_id}/clone", response_model=ActionOut, status_code=201)
def api_clone(
    action_id: str,
    data: ActionCloneRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.clone_action(db, current_user, action_id, data or ActionCloneRequest())


@router.get("/actions/{action_id}", response_model=ActionDetailOut)
def api_get_action(
    action_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.get_action(db, current_user, action_id)


@router.get("/actions/{action_id}/lineage", response_model=ActionLineageOut)
def api_action_lineage(
    action_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Action 跨周延续：周数、各周进度与风险文案。"""
    return svc.get_action_lineage(db, current_user, action_id)


@router.patch("/actions/{action_id}", response_model=ActionOut)
def api_update_action(
    action_id: str,
    data: ActionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.update_action(db, current_user, action_id, data)


@router.put("/actions/{action_id}/daily-updates", response_model=DailyUpdateOut)
def api_daily(
    action_id: str,
    data: DailyUpdateUpsert,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.upsert_daily_update(db, current_user, action_id, data)


@router.post(
    "/actions/{action_id}/corrections",
    response_model=ActionCorrectionOut,
    status_code=201,
)
def api_correction(
    action_id: str,
    data: ActionCorrectionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.add_correction(db, current_user, action_id, data)


# ── 企微日报 / 周报推送（Admin / Manager）────────────────────


@router.get("/push/status")
def api_push_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireRole(["Admin", "Manager"])),
):
    """查看 webhook 配置状态、快照与最近推送记录。"""
    push_svc.assert_can_push(current_user)
    return push_svc.push_status(db)


@router.post("/push/daily", response_model=PushResultOut)
async def api_push_daily(
    body: PushTriggerRequest = PushTriggerRequest(),
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireRole(["Admin", "Manager"])),
):
    """
    手动触发测试日报推送。

    dry_run=true：只生成文案不落库不发送；
    force=true：忽略「本日已推送」幂等（仍遵守无内容不发）。
    """
    push_svc.assert_can_push(current_user)
    result = await push_svc.push_daily(
        db,
        trigger=PUSH_TRIGGER_MANUAL,
        dry_run=body.dry_run,
        force=body.force,
    )
    return PushResultOut(**result.__dict__)


@router.post("/push/weekly", response_model=PushResultOut)
async def api_push_weekly(
    body: PushTriggerRequest = PushTriggerRequest(),
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireRole(["Admin", "Manager"])),
):
    """手动触发测试周报推送（短进展 + 增量/未解决风险）。"""
    push_svc.assert_can_push(current_user)
    result = await push_svc.push_weekly(
        db,
        trigger=PUSH_TRIGGER_MANUAL,
        dry_run=body.dry_run,
        force=body.force,
    )
    return PushResultOut(**result.__dict__)
