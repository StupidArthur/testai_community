"""
项目管理业务：Project/Domain/Task/Action、权限、看板、日更与更正。
"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from app.auth.models import User, UserRole
from app.test_manage.config import (
    ACTION_DONE_MIN_PROGRESS,
    ACTION_STATUSES,
    DAILY_EDIT_LOCK_HOUR,
    DAILY_EDIT_LOCK_MINUTE,
    HISTORY_WEEK_OPTIONS_MAX,
    PROJECT_STATUS_ACTIVE,
    PROJECT_STATUS_ARCHIVED,
    STATUS_CANCELLED,
    STATUS_DONE,
    STATUS_DRAFT,
    STATUS_PUBLISHED,
    TASK_STATUS_CANCELLED,
    TASK_STATUS_DONE,
    TASK_STATUS_DRAFT,
    TASK_STATUS_PUBLISHED,
    TASK_STATUSES_ALLOW_ACTION,
    TASK_STATUSES_USER,
    TASK_STATUSES,
    is_daily_edit_locked,
    now_tm,
    today_tm,
)
from app.test_manage.models import (
    TmAction,
    TmActionCorrection,
    TmDailyUpdate,
    TmDomain,
    TmProject,
    TmTask,
    TmTaskTester,
    TmTaskUpdateLog,
    TmTaskWeekProgress,
    TmWeekPeriod,
)
from app.test_manage.period import (
    get_daily_context_period,
    get_or_create_active_period,
    is_week_edit_locked,
)
from app.test_manage.schemas import (
    ActionCloneRequest,
    ActionCorrectionCreate,
    ActionCorrectionOut,
    ActionCreate,
    ActionDetailOut,
    ActionLineageOut,
    ActionLineageSegmentOut,
    ActionOut,
    ActionUpdate,
    BoardOut,
    BoardSummaryOut,
    BoardTaskOut,
    DailyUpdateOut,
    DailyUpdateUpsert,
    DomainCreate,
    DomainOut,
    ProjectCreate,
    ProjectOut,
    ProjectUpdate,
    TaskCreate,
    TaskDetailOut,
    TaskOut,
    TaskUpdate,
    TaskUpdateLogOut,
    TaskWeekProgressOut,
    TaskWeekProgressUpsert,
    UserBrief,
    WeekInfoOut,
    WeekOptionOut,
)
from app.test_manage.week import (
    current_week_start,
    daily_context_week_start,
    previous_week_start,
    week_end,
    week_key,
)


# ── 权限 ─────────────────────────────────────────────────────


def is_tm_admin(user: User) -> bool:
    """测试管理员：Admin 或 Manager。"""
    return user.role in (UserRole.Admin, UserRole.Manager)


def require_tm_admin(user: User) -> None:
    if not is_tm_admin(user):
        raise HTTPException(status_code=403, detail="仅测试管理员可操作")


def _tester_ids(task: TmTask) -> list[int]:
    return [t.user_id for t in (task.testers or [])]


def _action_owner_candidate_ids(task: TmTask) -> set[int]:
    """Action 本周负责人候选：Task 测试负责人 + 测试人员。"""
    return {task.lead_id, *_tester_ids(task)}


def _ensure_action_owner_candidate(task: TmTask, owner_id: int) -> None:
    """A1：owner 必须属于 Task 参与者集合。"""
    if owner_id not in _action_owner_candidate_ids(task):
        raise HTTPException(
            status_code=400,
            detail="Action 负责人只能从该 Task 的测试负责人或测试人员中选择",
        )


def is_task_lead(user: User, task: TmTask) -> bool:
    return task.lead_id == user.id


def can_edit_task(user: User, task: TmTask) -> bool:
    return is_tm_admin(user) or is_task_lead(user, task)


def can_add_action_to_task(task: TmTask) -> bool:
    """仅「测试中」且测试状态为进行中的 Task 可新建 / 复制本周 Action。"""
    from app.test_manage.req_stage import can_add_action_for_req_stage

    if task.status not in TASK_STATUSES_ALLOW_ACTION:
        return False
    return can_add_action_for_req_stage(getattr(task, "req_stage", None))


def can_edit_req_stage(user: User) -> bool:
    """需求进展与提测/测试时间：仅 Admin / Manager。"""
    return is_tm_admin(user)


def can_view_all(user: User) -> bool:
    return True  # 全员可读；编辑另判


def _ensure_users(db: Session, ids: list[int]) -> None:
    if not ids:
        return
    found = {u.id for u in db.query(User).filter(User.id.in_(set(ids))).all()}
    missing = set(ids) - found
    if missing:
        raise HTTPException(status_code=400, detail=f"用户不存在: {sorted(missing)}")


def _history_week_label(ws: datetime, we: datetime) -> str:
    return (
        f"{ws.strftime('%m-%d %H:%M')} → {we.strftime('%m-%d %H:%M')} · {week_key(ws)}"
    )


def snapshot_task_stages_for_week(db: Session, week_key_s: str) -> int:
    """
    固化指定周的需求进展快照（切周时调用）。
    已存在同 week_key+task_id 则覆盖。
    """
    from app.test_manage.config import REQ_STAGE_DEFAULT, TASK_STATUS_CANCELLED
    from app.test_manage.models import TmTaskStageSnapshot

    tasks = (
        db.query(TmTask)
        .filter(TmTask.status != TASK_STATUS_CANCELLED)
        .all()
    )
    existing = {
        (r.task_id, r.week_key): r
        for r in db.query(TmTaskStageSnapshot)
        .filter(TmTaskStageSnapshot.week_key == week_key_s)
        .all()
    }
    n = 0
    for task in tasks:
        key = (task.id, week_key_s)
        row = existing.get(key)
        if row is None:
            row = TmTaskStageSnapshot(task_id=task.id, week_key=week_key_s)
            db.add(row)
        row.req_stage = getattr(task, "req_stage", None) or REQ_STAGE_DEFAULT
        row.expected_handover_at = task.expected_handover_at
        row.actual_handover_at = task.actual_handover_at
        row.test_started_at = task.test_started_at
        row.expected_test_end_at = task.expected_test_end_at
        row.test_ended_at = task.test_ended_at
        n += 1
    db.flush()
    return n


def _stage_snapshots_map(db: Session, week_key_s: str) -> dict[str, dict]:
    from app.test_manage.models import TmTaskStageSnapshot

    rows = (
        db.query(TmTaskStageSnapshot)
        .filter(TmTaskStageSnapshot.week_key == week_key_s)
        .all()
    )
    return {
        r.task_id: {
            "req_stage": r.req_stage,
            "expected_handover_at": r.expected_handover_at,
            "actual_handover_at": r.actual_handover_at,
            "test_started_at": r.test_started_at,
            "expected_test_end_at": r.expected_test_end_at,
            "test_ended_at": r.test_ended_at,
        }
        for r in rows
    }


def list_history_week_options(
    db: Session,
    *,
    limit: int = HISTORY_WEEK_OPTIONS_MAX,
) -> list[WeekOptionOut]:
    """不含本周的最近 N 个业务周（优先读 tm_week_periods）。"""
    n = max(0, min(int(limit), HISTORY_WEEK_OPTIONS_MAX))
    active = get_or_create_active_period(db)
    rows = (
        db.query(TmWeekPeriod)
        .filter(TmWeekPeriod.week_key != active.week_key)
        .order_by(TmWeekPeriod.week_start.desc())
        .limit(n)
        .all()
    )
    if rows:
        return [
            WeekOptionOut(
                week_start=r.week_start,
                week_end=r.week_end,
                week_key=r.week_key,
                label=_history_week_label(r.week_start, r.week_end),
            )
            for r in rows
        ]
    # 兼容：尚无历史周期行时回退经典周
    ws = active.week_start
    out: list[WeekOptionOut] = []
    for _ in range(n):
        ws = previous_week_start(ws)
        we = week_end(ws)
        out.append(
            WeekOptionOut(
                week_start=ws,
                week_end=we,
                week_key=week_key(ws),
                label=_history_week_label(ws, we),
            )
        )
    return out


def get_week_info(db: Session, user: User | None, *, public: bool = False) -> WeekInfoOut:
    _ = public, user
    period = get_or_create_active_period(db)
    db.commit()
    return WeekInfoOut(
        week_start=period.week_start,
        week_end=period.week_end,
        week_key=period.week_key,
        history=list_history_week_options(db),
    )


def get_public_board(
    db: Session,
    *,
    week_start: datetime | None = None,
    project_id: str | None = None,
) -> BoardOut:
    """免鉴权只读大屏数据（权限字段全 false）。"""
    return get_board(
        db,
        user=None,
        week_start=week_start,
        project_id=project_id,
        public=True,
    )


def _writable_week_keys(db: Session) -> set[str]:
    active = get_or_create_active_period(db)
    daily = get_daily_context_period(db)
    return {active.week_key, daily.week_key}


def _assert_week_edit_open(db: Session) -> None:
    """
    周截止前编辑锁：周结束（默认周三 17:00）前 5 分钟起，
    停止 Action / Task 内容更新，切周后自动恢复。
    """
    if is_week_edit_locked(db):
        raise HTTPException(
            status_code=400,
            detail=(
                "本周内容已于周截止前 5 分钟锁定（默认周三 16:55），"
                "请于下周再更新；纠错请在下周补「更正说明」"
            ),
        )


def _is_writable_action_week(db: Session, action: TmAction) -> bool:
    """
    非「当前可写周」的 Action 一律只读。
    可写周 = 活动周 ∪ 日更上下文周（切日全天仍写结束周）。
    """
    return action.week_key in _writable_week_keys(db)


def _session_of(obj) -> Session:
    sess = Session.object_session(obj)
    if sess is None:
        raise HTTPException(status_code=500, detail="内部错误：对象未绑定会话")
    return sess


def _assert_writable_action_week(action: TmAction) -> None:
    if not _is_writable_action_week(_session_of(action), action):
        raise HTTPException(
            status_code=400,
            detail="历史周 Action 只读，不可编辑；请切回「本周」操作",
        )


def list_assignable_users(db: Session, user: User | None = None) -> list[UserBrief]:
    """登录用户可读简要用户列表（id/username/real_name），用于指派负责人/测试人员。"""
    _ = user
    rows = (
        db.query(User)
        .filter(User.username != "无")
        .order_by(User.username.asc())
        .all()
    )
    return [
        UserBrief(
            id=u.id,
            username=u.username,
            real_name=(getattr(u, "real_name", None) or "").strip(),
        )
        for u in rows
    ]


# ── Project / Domain ──────────────────────────────────────────


def create_project(db: Session, user: User, data: ProjectCreate) -> ProjectOut:
    require_tm_admin(user)
    row = TmProject(
        name=data.name.strip(),
        description=(data.description or "").strip() or None,
        status=PROJECT_STATUS_ACTIVE,
        created_by=user.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return ProjectOut.model_validate(row)


def list_projects(db: Session, *, include_archived: bool = False) -> list[ProjectOut]:
    q = db.query(TmProject)
    if not include_archived:
        q = q.filter(TmProject.status == PROJECT_STATUS_ACTIVE)
    return [ProjectOut.model_validate(r) for r in q.order_by(TmProject.created_at.desc()).all()]


def update_project(db: Session, user: User, project_id: str, data: ProjectUpdate) -> ProjectOut:
    require_tm_admin(user)
    row = db.query(TmProject).filter(TmProject.id == project_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="项目不存在")
    if data.name is not None:
        row.name = data.name.strip()
    if data.description is not None:
        row.description = data.description.strip() or None
    if data.status is not None:
        if data.status not in (PROJECT_STATUS_ACTIVE, PROJECT_STATUS_ARCHIVED):
            raise HTTPException(status_code=400, detail="无效项目状态")
        row.status = data.status
    db.commit()
    db.refresh(row)
    return ProjectOut.model_validate(row)


def archive_project(db: Session, user: User, project_id: str) -> ProjectOut:
    """归档项目：列表默认隐藏，数据保留可恢复。"""
    return update_project(
        db, user, project_id, ProjectUpdate(status=PROJECT_STATUS_ARCHIVED)
    )


def delete_project(db: Session, user: User, project_id: str) -> None:
    """
    永久删除项目及其领域 / Task / Action（含日更、更正、Task 周进度等）。
    仅 Admin/Manager；建错项目时使用。
    """
    require_tm_admin(user)
    row = db.query(TmProject).filter(TmProject.id == project_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="项目不存在")

    actions = db.query(TmAction).filter(TmAction.project_id == project_id).all()
    # 先断开跨 Action 延续引用，避免自引用阻碍删除
    for a in actions:
        a.source_action_id = None
    db.flush()
    for a in actions:
        db.delete(a)
    db.flush()

    tasks = db.query(TmTask).filter(TmTask.project_id == project_id).all()
    for t in tasks:
        db.delete(t)
    db.flush()

    domains = db.query(TmDomain).filter(TmDomain.project_id == project_id).all()
    for d in domains:
        db.delete(d)
    db.flush()

    db.delete(row)
    db.commit()


def create_domain(db: Session, user: User, project_id: str, data: DomainCreate) -> DomainOut:
    require_tm_admin(user)
    if not db.query(TmProject).filter(TmProject.id == project_id).first():
        raise HTTPException(status_code=404, detail="项目不存在")
    name = data.name.strip()
    if (
        db.query(TmDomain)
        .filter(TmDomain.project_id == project_id, TmDomain.name == name)
        .first()
    ):
        raise HTTPException(status_code=400, detail="该领域名称已存在")
    row = TmDomain(project_id=project_id, name=name, sort_order=data.sort_order)
    db.add(row)
    db.commit()
    db.refresh(row)
    return DomainOut.model_validate(row)


def list_domains(db: Session, project_id: str) -> list[DomainOut]:
    rows = (
        db.query(TmDomain)
        .filter(TmDomain.project_id == project_id)
        .order_by(TmDomain.sort_order.asc(), TmDomain.created_at.asc())
        .all()
    )
    return [DomainOut.model_validate(r) for r in rows]


# ── Task helpers ──────────────────────────────────────────────


def _load_task(db: Session, task_id: str) -> TmTask:
    task = (
        db.query(TmTask)
        .options(
            joinedload(TmTask.testers),
            joinedload(TmTask.update_logs),
            joinedload(TmTask.domain).joinedload(TmDomain.project),
        )
        .filter(TmTask.id == task_id)
        .first()
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task 不存在")
    return task


def _task_out(
    user: User | None,
    task: TmTask,
    *,
    force_readonly: bool = False,
    stage_override: dict | None = None,
) -> TaskOut:
    from app.test_manage.config import REQ_STAGE_DEFAULT
    from app.test_manage.req_stage import (
        normalize_req_stage,
        stage_node_date_summary,
    )

    project_name = None
    domain_name = None
    if task.domain:
        domain_name = task.domain.name
        if task.domain.project:
            project_name = task.domain.project.name
    readonly = force_readonly or user is None
    ov = stage_override or {}
    req_stage = normalize_req_stage(ov.get("req_stage", getattr(task, "req_stage", None)))
    expected_handover_at = ov.get(
        "expected_handover_at", getattr(task, "expected_handover_at", None)
    )
    actual_handover_at = ov.get(
        "actual_handover_at", getattr(task, "actual_handover_at", None)
    )
    test_started_at = ov.get("test_started_at", getattr(task, "test_started_at", None))
    expected_test_end_at = ov.get(
        "expected_test_end_at", getattr(task, "expected_test_end_at", None)
    )
    test_ended_at = ov.get("test_ended_at", getattr(task, "test_ended_at", None))
    summary = stage_node_date_summary(
        stage=req_stage,
        expected_handover_at=expected_handover_at,
        actual_handover_at=actual_handover_at,
        test_started_at=test_started_at,
        expected_test_end_at=expected_test_end_at,
        test_ended_at=test_ended_at,
    )
    return TaskOut(
        id=task.id,
        project_id=task.project_id,
        domain_id=task.domain_id,
        title=task.title,
        requirement=task.requirement or "",
        lead_id=task.lead_id,
        tester_ids=_tester_ids(task),
        status=task.status,
        req_stage=req_stage or REQ_STAGE_DEFAULT,
        expected_handover_at=expected_handover_at,
        actual_handover_at=actual_handover_at,
        test_started_at=test_started_at,
        expected_test_end_at=expected_test_end_at,
        test_ended_at=test_ended_at,
        stage_summary=summary,
        created_by=task.created_by,
        published_at=task.published_at,
        created_at=task.created_at,
        updated_at=task.updated_at,
        project_name=project_name,
        domain_name=domain_name,
        can_edit=False if readonly else can_edit_task(user, task),
        can_edit_req_stage=False if readonly else can_edit_req_stage(user),
        can_add_action=False if readonly else can_add_action_to_task(task),
    )


def _set_testers(db: Session, task: TmTask, tester_ids: list[int]) -> None:
    task.testers.clear()
    db.flush()
    for uid in dict.fromkeys(tester_ids):
        if uid == task.lead_id:
            continue
        task.testers.append(TmTaskTester(user_id=uid))


def create_task(db: Session, user: User, data: TaskCreate) -> TaskOut:
    require_tm_admin(user)
    domain = (
        db.query(TmDomain)
        .options(joinedload(TmDomain.project))
        .filter(TmDomain.id == data.domain_id)
        .first()
    )
    if not domain or domain.project_id != data.project_id:
        raise HTTPException(status_code=400, detail="项目与领域不匹配或不存在")
    tester_ids = list(dict.fromkeys(data.tester_ids or []))
    _ensure_users(db, [data.lead_id, *tester_ids])

    task = TmTask(
        project_id=data.project_id,
        domain_id=data.domain_id,
        title=data.title.strip(),
        requirement=(data.requirement or "").strip(),
        lead_id=data.lead_id,
        status=TASK_STATUS_PUBLISHED,
        created_by=user.id,
        published_at=now_tm(),
    )
    from app.test_manage.config import REQ_STAGE_DEFAULT
    from app.test_manage.req_stage import (
        normalize_req_stage,
        sync_test_status_for_stage,
        validate_req_stage_payload,
    )

    stage = normalize_req_stage(data.req_stage or REQ_STAGE_DEFAULT)
    validate_req_stage_payload(
        stage=stage,
        expected_handover_at=data.expected_handover_at,
        actual_handover_at=data.actual_handover_at,
        test_started_at=data.test_started_at,
        expected_test_end_at=data.expected_test_end_at,
        test_ended_at=data.test_ended_at,
    )
    task.req_stage = stage
    task.expected_handover_at = data.expected_handover_at
    task.actual_handover_at = data.actual_handover_at
    task.test_started_at = data.test_started_at
    task.expected_test_end_at = data.expected_test_end_at
    task.test_ended_at = data.test_ended_at
    synced = sync_test_status_for_stage(stage)
    if synced:
        task.status = synced
    db.add(task)
    db.flush()
    _set_testers(db, task, tester_ids)
    db.commit()
    return _task_out(user, _load_task(db, task.id))


def update_task(db: Session, user: User, task_id: str, data: TaskUpdate) -> TaskOut:
    task = _load_task(db, task_id)
    if not can_edit_task(user, task):
        raise HTTPException(status_code=403, detail="无权编辑该 Task")
    _assert_week_edit_open(db)

    changes: list[str] = []
    was_published = task.status == TASK_STATUS_PUBLISHED

    if data.title is not None and data.title.strip() != task.title:
        changes.append(f"标题: {task.title} → {data.title.strip()}")
        task.title = data.title.strip()
    if data.requirement is not None and data.requirement.strip() != (task.requirement or ""):
        changes.append("需求内容已更新")
        task.requirement = data.requirement.strip()
    if data.lead_id is not None and data.lead_id != task.lead_id:
        _ensure_users(db, [data.lead_id])
        changes.append(f"负责人 id: {task.lead_id} → {data.lead_id}")
        task.lead_id = data.lead_id
    if data.tester_ids is not None:
        _ensure_users(db, data.tester_ids)
        _set_testers(db, task, data.tester_ids)
        changes.append(f"测试人员: {data.tester_ids}")

    if data.status is not None:
        from app.test_manage.config import REQ_STAGES_SHOW_TEST_STATUS
        from app.test_manage.req_stage import normalize_req_stage

        cur_stage = normalize_req_stage(getattr(task, "req_stage", None))
        if cur_stage not in REQ_STAGES_SHOW_TEST_STATUS and data.status != task.status:
            raise HTTPException(
                status_code=400,
                detail="仅「测试中 / 测试完成」可改测试状态；请先由 Manager 调整需求进展",
            )
        if data.status not in TASK_STATUSES_USER:
            raise HTTPException(
                status_code=400,
                detail="测试状态仅支持：进行中(published)、已完成(done)",
            )
        if data.status != task.status:
            changes.append(f"测试状态: {task.status} → {data.status}")
            task.status = data.status
            if data.status == TASK_STATUS_PUBLISHED and not task.published_at:
                task.published_at = now_tm()

    # 需求进展（仅 Admin/Manager）
    stage_fields_touched = any(
        getattr(data, name) is not None
        for name in (
            "req_stage",
            "expected_handover_at",
            "actual_handover_at",
            "test_started_at",
            "expected_test_end_at",
            "test_ended_at",
        )
    )
    if stage_fields_touched:
        if not can_edit_req_stage(user):
            raise HTTPException(status_code=403, detail="仅 Admin/Manager 可改需求进展与提测时间")
        from app.test_manage.req_stage import (
            normalize_req_stage,
            sync_test_status_for_stage,
            validate_req_stage_payload,
        )

        new_stage = (
            normalize_req_stage(data.req_stage)
            if data.req_stage is not None
            else normalize_req_stage(getattr(task, "req_stage", None))
        )
        new_exp_h = (
            data.expected_handover_at
            if data.expected_handover_at is not None
            else task.expected_handover_at
        )
        new_act_h = (
            data.actual_handover_at
            if data.actual_handover_at is not None
            else task.actual_handover_at
        )
        new_start = (
            data.test_started_at if data.test_started_at is not None else task.test_started_at
        )
        new_exp_end = (
            data.expected_test_end_at
            if data.expected_test_end_at is not None
            else task.expected_test_end_at
        )
        new_end = data.test_ended_at if data.test_ended_at is not None else task.test_ended_at
        validate_req_stage_payload(
            stage=new_stage,
            expected_handover_at=new_exp_h,
            actual_handover_at=new_act_h,
            test_started_at=new_start,
            expected_test_end_at=new_exp_end,
            test_ended_at=new_end,
        )
        if new_stage != getattr(task, "req_stage", None):
            changes.append(f"需求进展: {task.req_stage} → {new_stage}")
        task.req_stage = new_stage
        task.expected_handover_at = new_exp_h
        task.actual_handover_at = new_act_h
        task.test_started_at = new_start
        task.expected_test_end_at = new_exp_end
        task.test_ended_at = new_end
        synced = sync_test_status_for_stage(new_stage)
        if synced and task.status != TASK_STATUS_CANCELLED and task.status != synced:
            changes.append(f"测试状态随需求进展同步: {task.status} → {synced}")
            task.status = synced

    if was_published and changes:
        summary = (data.change_summary or "").strip() or "；".join(changes)[:200]
        db.add(
            TmTaskUpdateLog(
                task_id=task.id,
                user_id=user.id,
                summary=summary,
                detail="\n".join(changes),
            )
        )

    db.commit()
    return _task_out(user, _load_task(db, task.id))


def archive_task(db: Session, user: User, task_id: str) -> TaskOut:
    """
    归档 Task：状态改为 cancelled，看板默认不再展示（数据保留）。
    管理员或该 Task lead 可操作。
    """
    task = _load_task(db, task_id)
    if not can_edit_task(user, task):
        raise HTTPException(status_code=403, detail="无权归档该 Task")
    if task.status == TASK_STATUS_CANCELLED:
        return _task_out(user, task)
    prev = task.status
    task.status = TASK_STATUS_CANCELLED
    db.add(
        TmTaskUpdateLog(
            task_id=task.id,
            user_id=user.id,
            summary="归档 Task",
            detail=f"状态: {prev} → {TASK_STATUS_CANCELLED}",
        )
    )
    db.commit()
    return _task_out(user, _load_task(db, task.id))


def delete_task(db: Session, user: User, task_id: str) -> None:
    """
    永久删除 Task 及其 Action（含日更、更正、周进度等）。
    管理员或该 Task lead 可操作。
    """
    task = _load_task(db, task_id)
    if not can_edit_task(user, task):
        raise HTTPException(status_code=403, detail="无权删除该 Task")

    actions = db.query(TmAction).filter(TmAction.task_id == task_id).all()
    for a in actions:
        a.source_action_id = None
    db.flush()
    # 其它 Action 若 source 指向本 Task 下条目，也已在上面清掉自链；
    # 仍可能有外 Task 指向这些 Action：一并断开
    ids = [a.id for a in actions]
    if ids:
        db.query(TmAction).filter(TmAction.source_action_id.in_(ids)).update(
            {TmAction.source_action_id: None}, synchronize_session=False
        )
        db.flush()
    for a in actions:
        db.delete(a)
    db.flush()
    db.delete(task)
    db.commit()


def get_task(db: Session, user: User, task_id: str) -> TaskDetailOut:
    task = _load_task(db, task_id)
    base = _task_out(user, task)
    logs = [
        TaskUpdateLogOut.model_validate(x)
        for x in sorted(
            task.update_logs or [],
            key=lambda z: z.created_at or datetime.min,
            reverse=True,
        )
    ]
    return TaskDetailOut(**base.model_dump(), update_logs=logs)


def list_tasks(
    db: Session,
    user: User,
    *,
    project_id: str | None = None,
    domain_id: str | None = None,
) -> list[TaskOut]:
    q = (
        db.query(TmTask)
        .options(
            joinedload(TmTask.testers),
            joinedload(TmTask.domain).joinedload(TmDomain.project),
        )
    )
    if project_id:
        q = q.filter(TmTask.project_id == project_id)
    if domain_id:
        q = q.filter(TmTask.domain_id == domain_id)
    rows = q.order_by(TmTask.updated_at.desc()).all()
    return [_task_out(user, t) for t in rows]


# ── Action helpers ────────────────────────────────────────────


def _load_action(db: Session, action_id: str) -> TmAction:
    action = (
        db.query(TmAction)
        .options(
            joinedload(TmAction.daily_updates),
            joinedload(TmAction.corrections),
            joinedload(TmAction.task).joinedload(TmTask.testers),
            joinedload(TmAction.task).joinedload(TmTask.domain).joinedload(TmDomain.project),
        )
        .filter(TmAction.id == action_id)
        .first()
    )
    if not action:
        raise HTTPException(status_code=404, detail="Action 不存在")
    return action


def _latest_progress(action: TmAction) -> tuple[int, str, bool]:
    """
    进度 / 风险文案 / 是否阻塞 —— 均取「最新一条」日更。

    风险已清除：最新日更 risk_blocker 为空。
    开放阻塞：有风险文案且 is_blocking=True（才进日报 / 阻塞 KPI）。
    """
    updates = list(action.daily_updates or [])
    if not updates:
        return 0, "", False

    def _sort_key(u: TmDailyUpdate) -> tuple:
        ts = u.updated_at or u.created_at or datetime.min
        return (u.report_date, ts)

    latest = max(updates, key=_sort_key)
    progress = int(latest.progress_percent)
    risk = (latest.risk_blocker or "").strip()
    is_blocking = bool(getattr(latest, "is_blocking", False)) and bool(risk)
    return progress, risk, is_blocking


def _has_daily_on(action: TmAction, day: date) -> bool:
    """Action 在指定自然日是否已有日更。"""
    for u in action.daily_updates or []:
        if u.report_date == day:
            return True
    return False


# Action 合法状态转移：不可取消；done 为终态不可重开
# （历史 cancelled 数据仍可读，但新操作不允许再取消）
_ACTION_STATUS_TRANSITIONS: dict[str, frozenset[str]] = {
    STATUS_DRAFT: frozenset({STATUS_PUBLISHED}),
    STATUS_PUBLISHED: frozenset({STATUS_DONE}),
    STATUS_DONE: frozenset(),
    STATUS_CANCELLED: frozenset(),  # 历史终态，不可再变更
}


def _ensure_action_status_transition(current: str, target: str) -> None:
    """拒绝非法状态跳转（含取消 Action、从终态重开）。"""
    if current == target:
        return
    if target == STATUS_CANCELLED:
        raise HTTPException(
            status_code=400,
            detail="Action 不支持取消，请将进度日更为 100% 后标记完成，或保留为草稿/进行中",
        )
    allowed = _ACTION_STATUS_TRANSITIONS.get(current)
    if allowed is None or target not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Action 状态不可从「{current}」变为「{target}」",
        )


def _ensure_progress_for_done(action: TmAction) -> None:
    """标记完成前校验：最新日更进度须达到 ACTION_DONE_MIN_PROGRESS。"""
    progress, _risk, _blocking = _latest_progress(action)
    if progress < ACTION_DONE_MIN_PROGRESS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"进度需达到 {ACTION_DONE_MIN_PROGRESS}% 才可标记完成"
                f"（当前 {progress}%），请先提交日更"
            ),
        )


def _can_mark_action_done(user: User, action: TmAction, progress: int) -> bool:
    """有状态变更权、进行中、且进度已满才可点完成。"""
    if not _is_writable_action_week(_session_of(action), action):
        return False
    if action.status != STATUS_PUBLISHED:
        return False
    if not _can_change_action_status(user, action):
        return False
    return progress >= ACTION_DONE_MIN_PROGRESS

def _can_change_action_status(user: User, action: TmAction) -> bool:
    """
    Action 状态变更权限：
    - Admin / Manager
    - 该 Task 测试负责人
    - 该 Action 本周负责人（自己的 Action）
    历史周一律不可改状态。
    """
    if not _is_writable_action_week(_session_of(action), action):
        return False
    if is_tm_admin(user):
        return True
    if action.task and is_task_lead(user, action.task):
        return True
    return action.owner_id == user.id


def _can_edit_action_fields(user: User, action: TmAction) -> bool:
    if not _is_writable_action_week(_session_of(action), action):
        return False
    if action.status != STATUS_DRAFT:
        return False
    task = action.task
    if not task:
        return is_tm_admin(user)
    return can_edit_task(user, task)


def _can_daily(user: User, action: TmAction) -> bool:
    """
    B1：仅「进行中」Action；Admin/Manager 或该 Action 负责人可写日更。
    已完成不可日更；过当日截止（默认 19:50）后窗口关闭。
    切日：日更只允许写「日报所属周」的 Action。
    """
    if action.status != STATUS_PUBLISHED:
        return False
    if is_daily_edit_locked():
        return False
    daily = get_daily_context_period(_session_of(action))
    if action.week_key != daily.week_key:
        return False
    return is_tm_admin(user) or action.owner_id == user.id


def _validate_daily_payload(action: TmAction, data: DailyUpdateUpsert) -> tuple[date, str, int]:
    """
    日更纪律：
    1. 只能写业务「今天」
    2. 进度说明去空白后非空
    3. 进度不可低于该 Action 当前最新进度
    4. 过截止时刻不可再写
    5. Action 须属于「日报所属周」（周三为刚结束周）
    """
    if is_daily_edit_locked():
        raise HTTPException(
            status_code=400,
            detail=(
                f"今日日更已于 {DAILY_EDIT_LOCK_HOUR:02d}:{DAILY_EDIT_LOCK_MINUTE:02d} 截止锁定，"
                "请明天再提交；纠错请用「更正说明」"
            ),
        )

    ctx = get_daily_context_period(_session_of(action))
    if action.week_key != ctx.week_key:
        raise HTTPException(
            status_code=400,
            detail=(
                "今日日更属于刚结束/进行中的汇报周（切日当天仍写结束周），"
                "请勿给新一周 Action 写日更"
            ),
        )

    today = today_tm()
    if data.report_date is not None and data.report_date != today:
        raise HTTPException(
            status_code=400,
            detail="日更只能填写当天，不能补写或改写历史日期",
        )
    report_date = today

    note = (data.progress_note or "").strip()
    if not note:
        raise HTTPException(status_code=400, detail="进度说明必填")

    prev_progress, _risk, _blocking = _latest_progress(action)
    if data.progress_percent < prev_progress:
        raise HTTPException(
            status_code=400,
            detail=(
                f"进度不可倒退（当前 {prev_progress}% → 提交 {data.progress_percent}%）；"
                "若需下调请用「更正说明」说明原因"
            ),
        )
    return report_date, note, data.progress_percent


def _can_correct(user: User, action: TmAction) -> bool:
    """发布后可追加更正说明（字段本身不可改）；历史周只读。"""
    if not _is_writable_action_week(_session_of(action), action):
        return False
    if action.status in (STATUS_DRAFT, STATUS_CANCELLED):
        return False
    if is_tm_admin(user):
        return True
    if action.task and is_task_lead(user, action.task):
        return True
    return action.owner_id == user.id


def _action_out(
    user: User | None,
    action: TmAction,
    *,
    force_readonly: bool = False,
) -> ActionOut:
    progress, risk, is_blocking = _latest_progress(action)
    task = action.task
    project_name = domain_name = task_title = None
    if task:
        task_title = task.title
        if task.domain:
            domain_name = task.domain.name
            if task.domain.project:
                project_name = task.domain.project.name
    readonly = force_readonly or user is None
    return ActionOut(
        id=action.id,
        task_id=action.task_id,
        project_id=action.project_id,
        domain_id=action.domain_id,
        week_start=action.week_start,
        week_key=action.week_key,
        title=action.title,
        owner_id=action.owner_id,
        test_content=action.test_content or "",
        environment=action.environment or "",
        status=action.status,
        source_action_id=action.source_action_id,
        created_by=action.created_by,
        published_at=action.published_at,
        due_at=action.due_at,
        created_at=action.created_at,
        updated_at=action.updated_at,
        progress_percent=progress,
        latest_risk=risk,
        latest_is_blocking=is_blocking,
        has_daily_today=_has_daily_on(action, today_tm()),
        task_title=task_title,
        project_name=project_name,
        domain_name=domain_name,
        can_edit_fields=False if readonly else _can_edit_action_fields(user, action),
        can_change_status=False if readonly else _can_change_action_status(user, action),
        can_mark_done=False if readonly else _can_mark_action_done(user, action, progress),
        can_daily=False if readonly else _can_daily(user, action),
        can_correct=False if readonly else _can_correct(user, action),
    )


def _sort_action_outs(actions: list[ActionOut]) -> list[ActionOut]:
    """
    Action 卡片列表顺序：进行中且今日未日更优先，同组按创建时间升序。
    """

    def _key(a: ActionOut) -> tuple[int, datetime, str]:
        missing = 0 if (a.status == STATUS_PUBLISHED and not a.has_daily_today) else 1
        created = a.created_at or datetime.min
        return (missing, created, a.id)

    return sorted(actions, key=_key)


def _publish_action(db: Session, action: TmAction) -> None:
    action.status = STATUS_PUBLISHED
    action.published_at = now_tm()
    if action.due_at is None:
        period = get_or_create_active_period(db)
        action.due_at = period.week_end


def create_action(db: Session, user: User, data: ActionCreate) -> ActionOut:
    task = _load_task(db, data.task_id)
    # 权限校验先行：无权限应得到 403，而非业务规则 400（避免向无关人员泄露任务状态细节）
    if not can_edit_task(user, task):
        raise HTTPException(status_code=403, detail="仅测试管理员或该 Task 负责人可创建 Action")
    if not can_add_action_to_task(task):
        if task.status == TASK_STATUS_DONE:
            raise HTTPException(status_code=400, detail="已完成的 Task 不能再创建 Action")
        from app.test_manage.req_stage import can_add_action_for_req_stage, req_stage_label

        if not can_add_action_for_req_stage(getattr(task, "req_stage", None)):
            raise HTTPException(
                status_code=400,
                detail=f"仅「测试中」可创建 Action（当前需求进展：{req_stage_label(task.req_stage)}）",
            )
        raise HTTPException(status_code=400, detail="仅测试进行中的 Task 可创建 Action")
    _assert_week_edit_open(db)

    owner_id = data.owner_id if data.owner_id is not None else task.lead_id
    _ensure_users(db, [owner_id])
    _ensure_action_owner_candidate(task, owner_id)
    if data.source_action_id:
        if not db.query(TmAction).filter(TmAction.id == data.source_action_id).first():
            raise HTTPException(status_code=400, detail="引用的 Action 不存在")

    period = get_or_create_active_period(db, user_id=user.id)
    action = TmAction(
        task_id=task.id,
        project_id=task.project_id,
        domain_id=task.domain_id,
        week_start=period.week_start,
        week_key=period.week_key,
        title=data.title.strip(),
        owner_id=owner_id,
        test_content=(data.test_content or "").strip(),
        environment=(data.environment or "").strip(),
        status=STATUS_DRAFT,
        source_action_id=data.source_action_id,
        created_by=user.id,
        due_at=period.week_end,
    )
    db.add(action)
    db.flush()
    if data.publish:
        _publish_action(db, action)
    db.commit()
    return _action_out(user, _load_action(db, action.id))


def clone_action(
    db: Session, user: User, source_id: str, data: ActionCloneRequest
) -> ActionOut:
    src = _load_action(db, source_id)
    return create_action(
        db,
        user,
        ActionCreate(
            task_id=src.task_id,
            title=(data.title or src.title).strip(),
            owner_id=src.owner_id,
            test_content=src.test_content or "",
            environment=src.environment or "",
            source_action_id=src.id,
            publish=data.publish,
        ),
    )


def update_action(db: Session, user: User, action_id: str, data: ActionUpdate) -> ActionOut:
    action = _load_action(db, action_id)
    _assert_writable_action_week(action)
    _assert_week_edit_open(db)

    # 状态变更：发布 / 完成（受状态机约束；不支持取消）
    if data.status is not None:
        if data.status not in ACTION_STATUSES:
            raise HTTPException(status_code=400, detail="无效状态")
        if not _can_change_action_status(user, action):
            raise HTTPException(status_code=403, detail="无权变更 Action 状态")
        _ensure_action_status_transition(action.status, data.status)
        if data.status == STATUS_DONE and action.status != STATUS_DONE:
            _ensure_progress_for_done(action)
        if data.status == STATUS_PUBLISHED and action.status == STATUS_DRAFT:
            _publish_action(db, action)
        else:
            action.status = data.status
            if data.status == STATUS_PUBLISHED and not action.published_at:
                _publish_action(db, action)

    # 字段：仅草稿可改（发布后本周负责人亦锁定，一周结束不再改派）
    field_touch = any(
        x is not None
        for x in (data.title, data.owner_id, data.test_content, data.environment)
    )
    if field_touch:
        if not _can_edit_action_fields(user, action):
            raise HTTPException(
                status_code=403,
                detail="Action 发布后字段锁定（含本周负责人），请用「更正说明」追加纠错",
            )
        if data.title is not None:
            action.title = data.title.strip()
        if data.owner_id is not None:
            _ensure_users(db, [data.owner_id])
            if action.task:
                _ensure_action_owner_candidate(action.task, data.owner_id)
            action.owner_id = data.owner_id
        if data.test_content is not None:
            action.test_content = data.test_content.strip()
        if data.environment is not None:
            action.environment = data.environment.strip()

    db.commit()
    return _action_out(user, _load_action(db, action.id))


def get_action(db: Session, user: User, action_id: str) -> ActionDetailOut:
    action = _load_action(db, action_id)
    base = _action_out(user, action)
    updates = sorted(
        action.daily_updates or [],
        key=lambda u: (u.report_date, u.updated_at or u.created_at or datetime.min),
        reverse=True,
    )
    corrections = sorted(
        action.corrections or [],
        key=lambda c: c.created_at or datetime.min,
        reverse=True,
    )
    return ActionDetailOut(
        **base.model_dump(),
        daily_updates=[DailyUpdateOut.model_validate(u) for u in updates],
        corrections=[ActionCorrectionOut.model_validate(c) for c in corrections],
    )


def upsert_daily_update(
    db: Session, user: User, action_id: str, data: DailyUpdateUpsert
) -> DailyUpdateOut:
    action = _load_action(db, action_id)
    if action.status != STATUS_PUBLISHED:
        raise HTTPException(status_code=403, detail="无权提交日更")
    if not (is_tm_admin(user) or action.owner_id == user.id):
        raise HTTPException(status_code=403, detail="无权提交日更")
    _assert_week_edit_open(db)

    report_date, note, progress = _validate_daily_payload(action, data)

    row = (
        db.query(TmDailyUpdate)
        .filter(
            TmDailyUpdate.action_id == action_id,
            TmDailyUpdate.report_date == report_date,
        )
        .first()
    )
    if row:
        row.user_id = user.id
        row.progress_percent = progress
        row.risk_blocker = (data.risk_blocker or "").strip()
        row.is_blocking = bool(data.is_blocking) and bool(row.risk_blocker)
        row.progress_note = note
    else:
        risk_txt = (data.risk_blocker or "").strip()
        row = TmDailyUpdate(
            action_id=action_id,
            user_id=user.id,
            report_date=report_date,
            progress_percent=progress,
            risk_blocker=risk_txt,
            is_blocking=bool(data.is_blocking) and bool(risk_txt),
            progress_note=note,
        )
        db.add(row)
    db.commit()
    db.refresh(row)
    return DailyUpdateOut.model_validate(row)


def add_correction(
    db: Session, user: User, action_id: str, data: ActionCorrectionCreate
) -> ActionCorrectionOut:
    action = _load_action(db, action_id)
    if not _can_correct(user, action):
        raise HTTPException(status_code=403, detail="无权追加更正说明")
    _assert_week_edit_open(db)
    row = TmActionCorrection(
        action_id=action_id, user_id=user.id, note=data.note.strip()
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return ActionCorrectionOut.model_validate(row)


def list_mine_actions(db: Session, user: User) -> list[ActionOut]:
    """
    「我的 Action」：仅当前周、负责人是当前用户的 Action。

    不含「仅因是 Task 测试人员/负责人」而挂上的他人 Action（那些在看板看）。
    """
    wk = get_or_create_active_period(db).week_key
    q = (
        db.query(TmAction)
        .options(
            joinedload(TmAction.daily_updates),
            joinedload(TmAction.task).joinedload(TmTask.testers),
            joinedload(TmAction.task).joinedload(TmTask.domain).joinedload(TmDomain.project),
        )
        .filter(TmAction.status.in_([STATUS_PUBLISHED, STATUS_DONE, STATUS_DRAFT]))
        .filter(TmAction.owner_id == user.id)
        .filter(TmAction.week_key == wk)
    )
    rows = q.order_by(TmAction.week_start.desc()).all()
    return _sort_action_outs([_action_out(user, a) for a in rows])


def list_clone_candidates(db: Session, user: User, task_id: str) -> list[ActionOut]:
    task = _load_task(db, task_id)
    if not can_edit_task(user, task):
        raise HTTPException(status_code=403, detail="无权查看可引用列表")
    if not can_add_action_to_task(task):
        return []
    active = get_or_create_active_period(db)
    prev = (
        db.query(TmWeekPeriod)
        .filter(TmWeekPeriod.week_end <= active.week_start)
        .order_by(TmWeekPeriod.week_end.desc())
        .first()
    )
    prev_key = prev.week_key if prev else week_key(previous_week_start(active.week_start))
    rows = (
        db.query(TmAction)
        .options(
            joinedload(TmAction.daily_updates),
            joinedload(TmAction.task).joinedload(TmTask.domain).joinedload(TmDomain.project),
        )
        .filter(TmAction.task_id == task_id)
        .filter(TmAction.week_key == prev_key)
        .filter(TmAction.status != STATUS_CANCELLED)
        .all()
    )
    return [_action_out(user, a) for a in rows]


def _action_avg_progress(act_outs: list[ActionOut]) -> int:
    visible = [x for x in act_outs if x.status != STATUS_DRAFT]
    pool = visible if visible else act_outs
    if not pool:
        return 0
    return int(round(sum(x.progress_percent for x in pool) / len(pool)))


def _resolve_task_week_progress(
    db: Session,
    *,
    task_id: str,
    week_key_s: str,
    act_outs: list[ActionOut],
) -> tuple[int, int, bool]:
    recommended = _action_avg_progress(act_outs)
    row = (
        db.query(TmTaskWeekProgress)
        .filter(
            TmTaskWeekProgress.task_id == task_id,
            TmTaskWeekProgress.week_key == week_key_s,
        )
        .first()
    )
    if row:
        return int(row.progress_percent), recommended, True
    return recommended, recommended, False


def get_task_week_progress(
    db: Session, user: User, task_id: str, *, week_key_s: str | None = None
) -> TaskWeekProgressOut:
    from app.test_manage.req_stage import can_add_action_for_req_stage

    task = _load_task(db, task_id)
    period = get_or_create_active_period(db)
    key = week_key_s or period.week_key
    acts = (
        db.query(TmAction)
        .options(joinedload(TmAction.daily_updates))
        .filter(TmAction.task_id == task_id, TmAction.week_key == key)
        .filter(TmAction.status != STATUS_CANCELLED)
        .all()
    )
    act_outs = [_action_out(user, a) for a in acts]
    display, recommended, manual = _resolve_task_week_progress(
        db, task_id=task_id, week_key_s=key, act_outs=act_outs
    )
    row = (
        db.query(TmTaskWeekProgress)
        .filter(
            TmTaskWeekProgress.task_id == task_id,
            TmTaskWeekProgress.week_key == key,
        )
        .first()
    )
    return TaskWeekProgressOut(
        task_id=task_id,
        week_key=key,
        progress_percent=display,
        recommended_progress=recommended,
        progress_is_manual=manual,
        note=(row.note if row else "") or "",
        updated_by=row.updated_by if row else None,
        updated_at=row.updated_at if row else None,
        can_edit=(
            can_edit_task(user, task)
            and key in _writable_week_keys(db)
            and can_add_action_for_req_stage(getattr(task, "req_stage", None))
        ),
    )


def upsert_task_week_progress(
    db: Session, user: User, task_id: str, data: TaskWeekProgressUpsert
) -> TaskWeekProgressOut:
    task = _load_task(db, task_id)
    if not can_edit_task(user, task):
        raise HTTPException(status_code=403, detail="仅测试管理员或 Task 测试负责人可填写周进度")
    _assert_week_edit_open(db)
    from app.test_manage.req_stage import can_add_action_for_req_stage, req_stage_label

    if not can_add_action_for_req_stage(getattr(task, "req_stage", None)):
        raise HTTPException(
            status_code=400,
            detail=f"仅「测试中」可填写本周 Task 进度（当前需求进展：{req_stage_label(task.req_stage)}）",
        )
    period = get_or_create_active_period(db)
    if period.week_key not in _writable_week_keys(db):
        raise HTTPException(status_code=400, detail="历史周不可填写 Task 进度")
    row = (
        db.query(TmTaskWeekProgress)
        .filter(
            TmTaskWeekProgress.task_id == task_id,
            TmTaskWeekProgress.week_key == period.week_key,
        )
        .first()
    )
    if not row:
        row = TmTaskWeekProgress(
            task_id=task_id,
            week_key=period.week_key,
            progress_percent=data.progress_percent,
            note=(data.note or "").strip(),
            updated_by=user.id,
        )
        db.add(row)
    else:
        row.progress_percent = data.progress_percent
        row.note = (data.note or "").strip()
        row.updated_by = user.id
    db.commit()
    return get_task_week_progress(db, user, task_id, week_key_s=period.week_key)


def get_action_lineage(db: Session, user: User, action_id: str) -> ActionLineageOut:
    _ = user
    start = _load_action(db, action_id)
    cur = start
    seen: set[str] = set()
    chain: list[TmAction] = []
    while cur and cur.id not in seen:
        seen.add(cur.id)
        chain.append(cur)
        if not cur.source_action_id:
            break
        cur = (
            db.query(TmAction)
            .options(joinedload(TmAction.daily_updates))
            .filter(TmAction.id == cur.source_action_id)
            .first()
        )
    chain.reverse()
    tip_ids = {chain[-1].id}
    while tip_ids:
        children = (
            db.query(TmAction)
            .options(joinedload(TmAction.daily_updates))
            .filter(TmAction.source_action_id.in_(tip_ids))
            .all()
        )
        tip_ids = set()
        for ch in children:
            if ch.id in seen:
                continue
            seen.add(ch.id)
            chain.append(ch)
            tip_ids.add(ch.id)

    segments: list[ActionLineageSegmentOut] = []
    for a in chain:
        progress, _risk, _blocking = _latest_progress(a)
        risks: list[str] = []
        for du in sorted(
            a.daily_updates or [],
            key=lambda u: (u.report_date, u.updated_at or u.created_at),
        ):
            r = (du.risk_blocker or "").strip()
            if r and r not in risks:
                risks.append(r)
        segments.append(
            ActionLineageSegmentOut(
                action_id=a.id,
                week_key=a.week_key,
                week_start=a.week_start,
                title=a.title,
                status=a.status,
                progress_percent=progress,
                risks=risks,
                is_current=a.id == start.id,
            )
        )
    return ActionLineageOut(
        action_id=start.id,
        weeks_count=len(segments),
        segments=segments,
    )


def get_board(
    db: Session,
    user: User | None,
    *,
    week_start: datetime | None = None,
    project_id: str | None = None,
    public: bool = False,
) -> BoardOut:
    """周 × Task 看板（项目管理首页）。全员可读；public=True 时免鉴权只读。"""
    if not public:
        if user is None:
            raise HTTPException(status_code=401, detail="未登录")
        _ = can_view_all(user)
    active = get_or_create_active_period(db)
    if week_start is not None:
        key = week_key(week_start)
        period_row = db.query(TmWeekPeriod).filter(TmWeekPeriod.week_key == key).first()
        ws = period_row.week_start if period_row else week_start
        we = period_row.week_end if period_row else week_end(week_start)
    else:
        key = active.week_key
        ws = active.week_start
        we = active.week_end

    q = (
        db.query(TmAction)
        .options(
            joinedload(TmAction.daily_updates),
            joinedload(TmAction.task).joinedload(TmTask.testers),
            joinedload(TmAction.task).joinedload(TmTask.domain).joinedload(TmDomain.project),
        )
        .filter(TmAction.week_key == key)
        .filter(TmAction.status != STATUS_CANCELLED)
    )
    if project_id:
        q = q.filter(TmAction.project_id == project_id)
    actions = q.all()

    by_task: dict[str, list[TmAction]] = {}
    for a in actions:
        by_task.setdefault(a.task_id, []).append(a)

    tq = (
        db.query(TmTask)
        .options(
            joinedload(TmTask.testers),
            joinedload(TmTask.domain).joinedload(TmDomain.project),
        )
        .filter(TmTask.status.in_([TASK_STATUS_PUBLISHED, TASK_STATUS_DONE]))
    )
    if project_id:
        tq = tq.filter(TmTask.project_id == project_id)
    tasks = {t.id: t for t in tq.all()}
    for tid in by_task:
        if tid not in tasks:
            tasks[tid] = _load_task(db, tid)

    viewing_history = key != active.week_key
    stage_map = _stage_snapshots_map(db, key) if viewing_history else {}

    board_tasks: list[BoardTaskOut] = []
    for tid, task in sorted(tasks.items(), key=lambda x: x[1].title):
        acts = by_task.get(tid, [])
        act_outs = _sort_action_outs(
            [_action_out(user, a, force_readonly=public) for a in acts]
        )
        risks = [
            x.latest_risk
            for x in act_outs
            if x.status == STATUS_PUBLISHED
            and bool(x.latest_is_blocking)
            and (x.latest_risk or "").strip()
        ]
        display, recommended, manual = _resolve_task_week_progress(
            db, task_id=tid, week_key_s=key, act_outs=act_outs
        )
        board_tasks.append(
            BoardTaskOut(
                task=_task_out(
                    user,
                    task,
                    force_readonly=public,
                    stage_override=stage_map.get(tid),
                ),
                actions=act_outs,
                week_progress_avg=display,
                progress_is_manual=manual,
                recommended_progress=recommended,
                risks=risks,
            )
        )

    if viewing_history:
        board_tasks = [b for b in board_tasks if b.actions]

    # 公开大屏 / Admin：展示全量；普通用户仍过滤无 Action 且与自己无关的空 Task
    if not viewing_history and not public and user is not None and not is_tm_admin(user):
        board_tasks = [
            b
            for b in board_tasks
            if b.actions
            or b.task.lead_id == user.id
            or user.id in b.task.tester_ids
        ]

    all_actions = [a for b in board_tasks for a in b.actions]
    risk_n = sum(
        1
        for a in all_actions
        if a.status == STATUS_PUBLISHED and bool(a.latest_is_blocking)
    )
    progress_avg = (
        int(round(sum(b.week_progress_avg for b in board_tasks) / len(board_tasks)))
        if board_tasks
        else 0
    )
    summary = BoardSummaryOut(
        task_count=len(board_tasks),
        action_count=len(all_actions),
        risk_action_count=risk_n,
        progress_avg=progress_avg,
        published_count=sum(1 for a in all_actions if a.status == STATUS_PUBLISHED),
        done_count=sum(1 for a in all_actions if a.status == STATUS_DONE),
        draft_count=sum(1 for a in all_actions if a.status == STATUS_DRAFT),
    )

    return BoardOut(
        week_start=ws,
        week_end=we,
        week_key=key,
        summary=summary,
        tasks=board_tasks,
    )
