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
)
from app.test_manage.schemas import (
    ActionCloneRequest,
    ActionCorrectionCreate,
    ActionCorrectionOut,
    ActionCreate,
    ActionDetailOut,
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
    """仅「进行中」Task 可新建 / 复制本周 Action；已完成不可。"""
    return task.status in TASK_STATUSES_ALLOW_ACTION


def can_view_all(user: User) -> bool:
    return True  # 全员可读；编辑另判


def _ensure_users(db: Session, ids: list[int]) -> None:
    if not ids:
        return
    found = {u.id for u in db.query(User).filter(User.id.in_(set(ids))).all()}
    missing = set(ids) - found
    if missing:
        raise HTTPException(status_code=400, detail=f"用户不存在: {sorted(missing)}")


def _history_week_label(ws: datetime) -> str:
    we = week_end(ws)
    return (
        f"{ws.strftime('%m-%d %H:%M')} → {we.strftime('%m-%d %H:%M')} · {week_key(ws)}"
    )


def list_history_week_options(
    *, limit: int = HISTORY_WEEK_OPTIONS_MAX
) -> list[WeekOptionOut]:
    """不含本周的最近 N 个业务周，供前端「历史」下拉。"""
    n = max(0, min(int(limit), HISTORY_WEEK_OPTIONS_MAX))
    ws = current_week_start()
    out: list[WeekOptionOut] = []
    for _ in range(n):
        ws = previous_week_start(ws)
        out.append(
            WeekOptionOut(
                week_start=ws,
                week_end=week_end(ws),
                week_key=week_key(ws),
                label=_history_week_label(ws),
            )
        )
    return out


def get_week_info() -> WeekInfoOut:
    ws = current_week_start()
    return WeekInfoOut(
        week_start=ws,
        week_end=week_end(ws),
        week_key=week_key(ws),
        history=list_history_week_options(),
    )


def _is_writable_action_week(action: TmAction) -> bool:
    """
    非「当前可写周」的 Action 一律只读。
    可写周 = current_week_start ∪ daily_context_week_start（覆盖周三切日口径）。
    """
    keys = {
        week_key(current_week_start()),
        week_key(daily_context_week_start()),
    }
    return action.week_key in keys


def _assert_writable_action_week(action: TmAction) -> None:
    if not _is_writable_action_week(action):
        raise HTTPException(
            status_code=400,
            detail="历史周 Action 只读，不可编辑；请切回「本周」操作",
        )


def list_assignable_users(db: Session, user: User) -> list[UserBrief]:
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


def _task_out(user: User, task: TmTask) -> TaskOut:
    project_name = None
    domain_name = None
    if task.domain:
        domain_name = task.domain.name
        if task.domain.project:
            project_name = task.domain.project.name
    return TaskOut(
        id=task.id,
        project_id=task.project_id,
        domain_id=task.domain_id,
        title=task.title,
        requirement=task.requirement or "",
        lead_id=task.lead_id,
        tester_ids=_tester_ids(task),
        status=task.status,
        created_by=task.created_by,
        published_at=task.published_at,
        created_at=task.created_at,
        updated_at=task.updated_at,
        project_name=project_name,
        domain_name=domain_name,
        can_edit=can_edit_task(user, task),
        can_add_action=can_add_action_to_task(task),
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
    db.add(task)
    db.flush()
    _set_testers(db, task, tester_ids)
    db.commit()
    return _task_out(user, _load_task(db, task.id))


def update_task(db: Session, user: User, task_id: str, data: TaskUpdate) -> TaskOut:
    task = _load_task(db, task_id)
    if not can_edit_task(user, task):
        raise HTTPException(status_code=403, detail="无权编辑该 Task")

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
        if data.status not in TASK_STATUSES_USER:
            raise HTTPException(
                status_code=400,
                detail="Task 状态仅支持：进行中(published)、已完成(done)",
            )
        if data.status != task.status:
            changes.append(f"状态: {task.status} → {data.status}")
            task.status = data.status
            if data.status == TASK_STATUS_PUBLISHED and not task.published_at:
                task.published_at = now_tm()

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


def _latest_progress(action: TmAction) -> tuple[int, str]:
    """
    进度与风险均取「最新一条」日更（按 report_date、再按更新时间）。

    已解决语义：最新日更的 risk_blocker 为空 → 风险已清除（不再沿用历史风险文案）。
    """
    updates = list(action.daily_updates or [])
    if not updates:
        return 0, ""

    def _sort_key(u: TmDailyUpdate) -> tuple:
        ts = u.updated_at or u.created_at or datetime.min
        return (u.report_date, ts)

    latest = max(updates, key=_sort_key)
    progress = int(latest.progress_percent)
    risk = (latest.risk_blocker or "").strip()
    return progress, risk


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
    progress, _ = _latest_progress(action)
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
    if not _is_writable_action_week(action):
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
    if not _is_writable_action_week(action):
        return False
    if is_tm_admin(user):
        return True
    if action.task and is_task_lead(user, action.task):
        return True
    return action.owner_id == user.id


def _can_edit_action_fields(user: User, action: TmAction) -> bool:
    if not _is_writable_action_week(action):
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
    周三切周日：日更只允许写「日报所属周」（刚结束周）的 Action，不写新一周。
    """
    if action.status != STATUS_PUBLISHED:
        return False
    if is_daily_edit_locked():
        return False
    if action.week_key != week_key(daily_context_week_start()):
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

    ctx_key = week_key(daily_context_week_start())
    if action.week_key != ctx_key:
        raise HTTPException(
            status_code=400,
            detail=(
                "今日日更属于刚结束/进行中的汇报周（切周日周三全天仍写上一周），"
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

    prev_progress, _ = _latest_progress(action)
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
    if not _is_writable_action_week(action):
        return False
    if action.status in (STATUS_DRAFT, STATUS_CANCELLED):
        return False
    if is_tm_admin(user):
        return True
    if action.task and is_task_lead(user, action.task):
        return True
    return action.owner_id == user.id


def _action_out(user: User, action: TmAction) -> ActionOut:
    progress, risk = _latest_progress(action)
    task = action.task
    project_name = domain_name = task_title = None
    if task:
        task_title = task.title
        if task.domain:
            domain_name = task.domain.name
            if task.domain.project:
                project_name = task.domain.project.name
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
        task_title=task_title,
        project_name=project_name,
        domain_name=domain_name,
        can_edit_fields=_can_edit_action_fields(user, action),
        can_change_status=_can_change_action_status(user, action),
        can_mark_done=_can_mark_action_done(user, action, progress),
        can_daily=_can_daily(user, action),
        can_correct=_can_correct(user, action),
    )


def _publish_action(action: TmAction) -> None:
    action.status = STATUS_PUBLISHED
    action.published_at = now_tm()
    if action.due_at is None:
        action.due_at = week_end(action.week_start)


def create_action(db: Session, user: User, data: ActionCreate) -> ActionOut:
    task = _load_task(db, data.task_id)
    if not can_add_action_to_task(task):
        if task.status == TASK_STATUS_DONE:
            raise HTTPException(status_code=400, detail="已完成的 Task 不能再创建 Action")
        raise HTTPException(status_code=400, detail="仅进行中的 Task 可创建 Action")
    if not can_edit_task(user, task):
        raise HTTPException(status_code=403, detail="仅测试管理员或该 Task 负责人可创建 Action")

    owner_id = data.owner_id if data.owner_id is not None else task.lead_id
    _ensure_users(db, [owner_id])
    _ensure_action_owner_candidate(task, owner_id)
    if data.source_action_id:
        if not db.query(TmAction).filter(TmAction.id == data.source_action_id).first():
            raise HTTPException(status_code=400, detail="引用的 Action 不存在")

    ws = current_week_start()
    action = TmAction(
        task_id=task.id,
        project_id=task.project_id,
        domain_id=task.domain_id,
        week_start=ws,
        week_key=week_key(ws),
        title=data.title.strip(),
        owner_id=owner_id,
        test_content=(data.test_content or "").strip(),
        environment=(data.environment or "").strip(),
        status=STATUS_DRAFT,
        source_action_id=data.source_action_id,
        created_by=user.id,
        due_at=week_end(ws),
    )
    db.add(action)
    db.flush()
    if data.publish:
        _publish_action(action)
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
            _publish_action(action)
        else:
            action.status = data.status
            if data.status == STATUS_PUBLISHED and not action.published_at:
                _publish_action(action)

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
        row.progress_note = note
    else:
        row = TmDailyUpdate(
            action_id=action_id,
            user_id=user.id,
            report_date=report_date,
            progress_percent=progress,
            risk_blocker=(data.risk_blocker or "").strip(),
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
    wk = week_key(current_week_start())
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
    return [_action_out(user, a) for a in rows]


def list_clone_candidates(db: Session, user: User, task_id: str) -> list[ActionOut]:
    task = _load_task(db, task_id)
    if not can_edit_task(user, task):
        raise HTTPException(status_code=403, detail="无权查看可引用列表")
    if not can_add_action_to_task(task):
        return []
    prev_key = week_key(previous_week_start())
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


def get_board(
    db: Session,
    user: User,
    *,
    week_start: datetime | None = None,
    project_id: str | None = None,
) -> BoardOut:
    """周 × Task 看板（项目管理首页）。全员可读。"""
    _ = can_view_all(user)
    ws = week_start or current_week_start()
    key = week_key(ws)
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

    # 本周无 Action 的已发布 Task 也展示空卡片（便于补建）
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
            t = _load_task(db, tid)
            tasks[tid] = t

    board_tasks: list[BoardTaskOut] = []
    for tid, task in sorted(tasks.items(), key=lambda x: x[1].title):
        acts = by_task.get(tid, [])
        act_outs = [_action_out(user, a) for a in acts]
        # 开放风险仅计「进行中」Action（完成/草稿遗留文案不计入大屏与 KPI）
        risks = [
            x.latest_risk
            for x in act_outs
            if x.status == STATUS_PUBLISHED and (x.latest_risk or "").strip()
        ]
        avg = (
            int(round(sum(x.progress_percent for x in act_outs) / len(act_outs)))
            if act_outs
            else 0
        )
        board_tasks.append(
            BoardTaskOut(
                task=_task_out(user, task),
                actions=act_outs,
                week_progress_avg=avg,
                risks=risks,
            )
        )

    # 历史周：只展示该周确有 Action 的 Task（避免空卡片刷屏）
    viewing_history = key != week_key(current_week_start())
    if viewing_history:
        board_tasks = [b for b in board_tasks if b.actions]

    # 当前周：非管理员只保留有 Action 或自己参与的 Task
    if not viewing_history and not is_tm_admin(user):
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
        if a.status == STATUS_PUBLISHED and (a.latest_risk or "").strip()
    )
    progress_avg = (
        int(round(sum(a.progress_percent for a in all_actions) / len(all_actions)))
        if all_actions
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
        week_end=week_end(ws),
        week_key=key,
        summary=summary,
        tasks=board_tasks,
    )
