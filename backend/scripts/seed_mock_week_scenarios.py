"""
在 TPT v2.1 下按真实 Domain（平台 / Agent / 交付 / 定制）灌「上周 + 本汇报周」场景数据。

会删除错误的「Mock Scenario Demo」项目；不改 Domain 名称体系。

    python scripts/seed_mock_week_scenarios.py
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

try:
    from dotenv import load_dotenv

    load_dotenv(_BACKEND.parent / ".env")
    load_dotenv(_BACKEND / ".env")
except Exception:
    pass

from sqlalchemy.orm import Session

from app.auth.models import User, UserRole
from app.auth.service import hash_password
from app.platform.database import SessionLocal
from app.test_manage.config import (
    PROJECT_STATUS_ACTIVE,
    REQ_STAGE_TEST_DONE,
    REQ_STAGE_TESTING,
    STATUS_CANCELLED,
    STATUS_DONE,
    STATUS_DRAFT,
    STATUS_PUBLISHED,
    TASK_STATUS_CANCELLED,
    TASK_STATUS_DONE,
    TASK_STATUS_DRAFT,
    TASK_STATUS_PUBLISHED,
    now_tm,
)
from app.test_manage.models import (
    TmAction,
    TmActionCorrection,
    TmDailyUpdate,
    TmDomain,
    TmProject,
    TmPushRun,
    TmPushSnapshot,
    TmTask,
    TmTaskTester,
    TmTaskWeekProgress,
)
from app.test_manage.period import get_daily_context_period
from app.test_manage.week import (
    previous_week_start,
    week_end,
    week_key,
)

PROJECT_NAME = "TPT v2.1"
BAD_PROJECT_NAME = "Mock Scenario Demo"
DEFAULT_PASSWORD = "123456"
DOMAIN_NAMES = ("平台", "Agent", "交付", "定制")


def _ensure_user(db: Session, username: str, real_name: str) -> int:
    row = db.query(User).filter(User.username == username).first()
    if not row:
        row = User(
            username=username,
            password_hash=hash_password(DEFAULT_PASSWORD),
            role=UserRole.Engineer,
            real_name=real_name,
        )
        db.add(row)
        db.flush()
    elif not (row.real_name or "").strip():
        row.real_name = real_name
    return int(row.id)


def _delete_project(db: Session, name: str) -> None:
    proj = db.query(TmProject).filter(TmProject.name == name).first()
    if not proj:
        return
    tasks = db.query(TmTask).filter(TmTask.project_id == proj.id).all()
    tids = [t.id for t in tasks]
    if tids:
        aids = [
            a.id for a in db.query(TmAction).filter(TmAction.task_id.in_(tids)).all()
        ]
        if aids:
            db.query(TmDailyUpdate).filter(TmDailyUpdate.action_id.in_(aids)).delete(
                synchronize_session=False
            )
            db.query(TmActionCorrection).filter(
                TmActionCorrection.action_id.in_(aids)
            ).delete(synchronize_session=False)
            db.query(TmAction).filter(TmAction.id.in_(aids)).delete(
                synchronize_session=False
            )
        db.query(TmTaskTester).filter(TmTaskTester.task_id.in_(tids)).delete(
            synchronize_session=False
        )
        db.query(TmTask).filter(TmTask.id.in_(tids)).delete(synchronize_session=False)
    db.query(TmDomain).filter(TmDomain.project_id == proj.id).delete(
        synchronize_session=False
    )
    db.delete(proj)
    print(f"  deleted project {name!r}")


def _purge_bad_domains(db: Session, project_id: str) -> None:
    """删除错误的演示 Domain（新建领域 / 延续领域等），避免污染真实四域。"""
    bad_names = ("新建领域", "延续领域", "新建", "延续")
    rows = (
        db.query(TmDomain)
        .filter(TmDomain.project_id == project_id, TmDomain.name.in_(bad_names))
        .all()
    )
    for d in rows:
        tasks = db.query(TmTask).filter(TmTask.domain_id == d.id).all()
        tids = [t.id for t in tasks]
        if tids:
            aids = [
                a.id for a in db.query(TmAction).filter(TmAction.task_id.in_(tids)).all()
            ]
            if aids:
                db.query(TmDailyUpdate).filter(TmDailyUpdate.action_id.in_(aids)).delete(
                    synchronize_session=False
                )
                db.query(TmActionCorrection).filter(
                    TmActionCorrection.action_id.in_(aids)
                ).delete(synchronize_session=False)
                db.query(TmAction).filter(TmAction.id.in_(aids)).delete(
                    synchronize_session=False
                )
            db.query(TmTaskTester).filter(TmTaskTester.task_id.in_(tids)).delete(
                synchronize_session=False
            )
            db.query(TmTask).filter(TmTask.id.in_(tids)).delete(synchronize_session=False)
        db.delete(d)
        print(f"  deleted bad domain {d.name!r}")


def _ensure_domains(db: Session, project_id: str) -> dict[str, TmDomain]:
    _purge_bad_domains(db, project_id)
    out: dict[str, TmDomain] = {}
    for i, name in enumerate(DOMAIN_NAMES):
        d = (
            db.query(TmDomain)
            .filter(TmDomain.project_id == project_id, TmDomain.name == name)
            .first()
        )
        if not d:
            d = TmDomain(project_id=project_id, name=name, sort_order=i + 1)
            db.add(d)
            db.flush()
            print(f"  + domain {name}")
        out[name] = d
    return out


def _find_or_create_task(
    db: Session,
    *,
    project_id: str,
    domain: TmDomain,
    title: str,
    requirement: str,
    lead_id: int,
    tester_ids: list[int],
    status: str = TASK_STATUS_PUBLISHED,
) -> TmTask:
    today = date.today()
    if status == TASK_STATUS_DONE:
        req_stage = REQ_STAGE_TEST_DONE
        test_started_at = today - timedelta(days=10)
        expected_test_end_at = today - timedelta(days=2)
        test_ended_at = today - timedelta(days=1)
    else:
        req_stage = REQ_STAGE_TESTING
        test_started_at = today - timedelta(days=3)
        expected_test_end_at = today + timedelta(days=4)
        test_ended_at = None
    row = (
        db.query(TmTask)
        .filter(TmTask.project_id == project_id, TmTask.title == title)
        .first()
    )
    if row:
        row.domain_id = domain.id
        row.requirement = requirement
        row.lead_id = lead_id
        row.status = status
        row.req_stage = req_stage
        row.test_started_at = test_started_at
        row.expected_test_end_at = expected_test_end_at
        row.test_ended_at = test_ended_at
        db.query(TmTaskTester).filter(TmTaskTester.task_id == row.id).delete(
            synchronize_session=False
        )
        for uid in tester_ids:
            if uid != lead_id:
                db.add(TmTaskTester(task_id=row.id, user_id=uid))
        db.flush()
        return row
    row = TmTask(
        project_id=project_id,
        domain_id=domain.id,
        title=title,
        requirement=requirement,
        lead_id=lead_id,
        status=status,
        req_stage=req_stage,
        test_started_at=test_started_at,
        expected_test_end_at=expected_test_end_at,
        test_ended_at=test_ended_at,
        created_by=lead_id,
        published_at=now_tm() if status == TASK_STATUS_PUBLISHED else None,
    )
    db.add(row)
    db.flush()
    for uid in tester_ids:
        if uid != lead_id:
            db.add(TmTaskTester(task_id=row.id, user_id=uid))
    db.flush()
    return row


def _upsert_week_progress(
    db: Session,
    *,
    task_id: str,
    week_key_s: str,
    progress: int,
    note: str,
    updated_by: int,
) -> None:
    """手填 Task 周进度（大屏 progress_is_manual=True）。"""
    row = (
        db.query(TmTaskWeekProgress)
        .filter(
            TmTaskWeekProgress.task_id == task_id,
            TmTaskWeekProgress.week_key == week_key_s,
        )
        .first()
    )
    if row:
        row.progress_percent = int(progress)
        row.note = note
        row.updated_by = updated_by
    else:
        db.add(
            TmTaskWeekProgress(
                task_id=task_id,
                week_key=week_key_s,
                progress_percent=int(progress),
                note=note,
                updated_by=updated_by,
            )
        )
    db.flush()


def _purge_scenario_week_progress(db: Session, project_id: str, week_key_s: str) -> None:
    """清本项目【场景】Task 在指定周的手填进度，便于重灌。"""
    tids = [
        t.id
        for t in db.query(TmTask)
        .filter(TmTask.project_id == project_id, TmTask.title.like("【场景】%"))
        .all()
    ]
    if not tids:
        return
    db.query(TmTaskWeekProgress).filter(
        TmTaskWeekProgress.task_id.in_(tids),
        TmTaskWeekProgress.week_key == week_key_s,
    ).delete(synchronize_session=False)


def _purge_scenario_actions(db: Session, task_id: str) -> None:
    """只清带「【场景】」前缀的 Action，保留真实计划灌入的项。"""
    rows = (
        db.query(TmAction)
        .filter(TmAction.task_id == task_id, TmAction.title.like("【场景】%"))
        .all()
    )
    aids = [a.id for a in rows]
    if not aids:
        return
    db.query(TmDailyUpdate).filter(TmDailyUpdate.action_id.in_(aids)).delete(
        synchronize_session=False
    )
    db.query(TmActionCorrection).filter(TmActionCorrection.action_id.in_(aids)).delete(
        synchronize_session=False
    )
    db.query(TmAction).filter(TmAction.id.in_(aids)).delete(synchronize_session=False)


def _mk_action(
    db: Session,
    *,
    task: TmTask,
    title: str,
    owner_id: int,
    week_start: datetime,
    status: str,
    test_content: str = "",
    environment: str = "",
    week_key_s: str | None = None,
) -> TmAction:
    """创建 Action；week_key 优先用传入的业务周键（与看板活动周对齐）。"""
    wk = (week_key_s or "").strip() or week_key(week_start)
    a = TmAction(
        task_id=task.id,
        project_id=task.project_id,
        domain_id=task.domain_id,
        week_start=week_start,
        week_key=wk,
        title=title,
        owner_id=owner_id,
        test_content=test_content,
        environment=environment,
        status=status,
        created_by=owner_id,
        published_at=week_start if status != STATUS_DRAFT else None,
        due_at=week_end(week_start),
    )
    db.add(a)
    db.flush()
    return a


def _add_daily(
    db: Session,
    *,
    action: TmAction,
    user_id: int,
    report_date: date,
    progress: int,
    risk: str,
    note: str,
    is_blocking: bool = False,
) -> None:
    """写入日更；有风险且 is_blocking 才计入大屏「有阻塞」。"""
    risk_text = (risk or "").strip()
    db.add(
        TmDailyUpdate(
            action_id=action.id,
            user_id=user_id,
            report_date=report_date,
            progress_percent=progress,
            risk_blocker=risk_text,
            is_blocking=bool(is_blocking and risk_text),
            progress_note=note,
        )
    )


def seed() -> None:
    db = SessionLocal()
    try:
        print("== seed mock week scenarios (real domains) ==")
        hj = _ensure_user(db, "hj", "黄婧")
        xj = _ensure_user(db, "xiaojun", "袁小君")
        zw = _ensure_user(db, "zhangwen", "张雯")
        db.commit()

        period = get_daily_context_period(db)
        report_ws = period.week_start
        prev_ws = previous_week_start(report_ws)
        today = now_tm().date()
        prev_mid = (prev_ws + timedelta(days=3)).date()
        print(f"  report_week={period.week_key} prev_week={week_key(prev_ws)} today={today}")
        print(f"  week_window={report_ws} -> {period.week_end}")

        _delete_project(db, BAD_PROJECT_NAME)

        proj = db.query(TmProject).filter(TmProject.name == PROJECT_NAME).first()
        if not proj:
            proj = TmProject(
                name=PROJECT_NAME,
                description="真实计划 + 场景 mock",
                status=PROJECT_STATUS_ACTIVE,
                created_by=hj,
            )
            db.add(proj)
            db.flush()
            print(f"  + project {PROJECT_NAME}")

        domains = _ensure_domains(db, proj.id)
        _purge_scenario_week_progress(db, proj.id, period.week_key)

        # 清空推送快照，便于日报「新增」
        n1 = db.query(TmPushSnapshot).delete(synchronize_session=False)
        n2 = db.query(TmPushRun).delete(synchronize_session=False)
        print(f"  cleared push snapshots={n1} runs={n2}")

        # ── 平台：旧 Task 跨周 ──
        t_plat = _find_or_create_task(
            db,
            project_id=proj.id,
            domain=domains["平台"],
            title="【场景】平台稳定性回归（跨周旧Task）",
            requirement="跨周延续：上周有完成/取消/遗留；本周继续压测。",
            lead_id=hj,
            tester_ids=[xj, zw],
        )
        _purge_scenario_actions(db, t_plat.id)

        a = _mk_action(
            db,
            task=t_plat,
            title="【场景】上周-接口冒烟（已完成）",
            owner_id=hj,
            week_start=prev_ws,
            status=STATUS_DONE,
            test_content="冒烟全过",
            environment="staging",
        )
        _add_daily(
            db, action=a, user_id=hj, report_date=prev_mid, progress=100, risk="", note="上周收尾完成"
        )

        _mk_action(
            db,
            task=t_plat,
            title="【场景】上周-历史取消项",
            owner_id=xj,
            week_start=prev_ws,
            status=STATUS_CANCELLED,
            test_content="计划取消",
            environment="—",
        )

        a = _mk_action(
            db,
            task=t_plat,
            title="【场景】上周-未完成遗留（有风险）",
            owner_id=zw,
            week_start=prev_ws,
            status=STATUS_PUBLISHED,
            test_content="上周未做完",
            environment="staging",
        )
        _add_daily(
            db,
            action=a,
            user_id=zw,
            report_date=prev_mid,
            progress=40,
            risk="证书过期",
            note="上周卡住",
        )

        a = _mk_action(
            db,
            task=t_plat,
            title="【场景】本周-进行中有阻塞",
            owner_id=hj,
            week_start=report_ws,
            status=STATUS_PUBLISHED,
            test_content="压测告警",
            environment="perf",
        )
        _add_daily(
            db,
            action=a,
            user_id=hj,
            report_date=today,
            progress=45,
            risk="压测机磁盘满",
            note="阻塞未解除",
            is_blocking=True,
        )

        a = _mk_action(
            db,
            task=t_plat,
            title="【场景】本周-第二阻塞（同Task多阻塞）",
            owner_id=xj,
            week_start=report_ws,
            status=STATUS_PUBLISHED,
            test_content="监控告警误报排查",
            environment="perf",
        )
        _add_daily(
            db,
            action=a,
            user_id=xj,
            report_date=today,
            progress=25,
            risk="告警通道打满，值班无法收敛",
            note="需扩容",
            is_blocking=True,
        )

        a = _mk_action(
            db,
            task=t_plat,
            title="【场景】本周-有风险未勾阻塞",
            owner_id=zw,
            week_start=report_ws,
            status=STATUS_PUBLISHED,
            test_content="日志采样",
            environment="staging",
        )
        _add_daily(
            db,
            action=a,
            user_id=zw,
            report_date=today,
            progress=55,
            risk="偶发超时，先观察不阻塞",
            note="风险观察中",
            is_blocking=False,
        )

        a = _mk_action(
            db,
            task=t_plat,
            title="【场景】本周-未日更进行中",
            owner_id=hj,
            week_start=report_ws,
            status=STATUS_PUBLISHED,
            test_content="容量评估",
            environment="perf",
        )
        # 仅昨日日更 → 今日视角为未日更
        _add_daily(
            db,
            action=a,
            user_id=hj,
            report_date=today - timedelta(days=1),
            progress=15,
            risk="",
            note="昨日写过，今日未更",
        )

        a = _mk_action(
            db,
            task=t_plat,
            title="【场景】本周-风险已解除",
            owner_id=xj,
            week_start=report_ws,
            status=STATUS_PUBLISHED,
            test_content="缺陷复测",
            environment="staging",
        )
        _add_daily(
            db, action=a, user_id=xj, report_date=today, progress=80, risk="", note="风险已清"
        )

        a = _mk_action(
            db,
            task=t_plat,
            title="【场景】本周-已完成100%",
            owner_id=hj,
            week_start=report_ws,
            status=STATUS_DONE,
            test_content="验收",
            environment="staging",
        )
        _add_daily(
            db, action=a, user_id=hj, report_date=today, progress=100, risk="", note="验收通过"
        )

        _mk_action(
            db,
            task=t_plat,
            title="【场景】本周-草稿未发布",
            owner_id=zw,
            week_start=report_ws,
            status=STATUS_DRAFT,
            test_content="待确认",
            environment="",
        )

        # ── Agent：本周新建 Task ──
        t_agent = _find_or_create_task(
            db,
            project_id=proj.id,
            domain=domains["Agent"],
            title="【场景】Agent 联调专项（本周新Task）",
            requirement="本周新建，无上周 Action；多 Action 覆盖阻塞/正常/低进度。",
            lead_id=xj,
            tester_ids=[hj, zw],
        )
        _purge_scenario_actions(db, t_agent.id)
        a = _mk_action(
            db,
            task=t_agent,
            title="【场景】本周-联调阻塞（新增风险）",
            owner_id=xj,
            week_start=report_ws,
            status=STATUS_PUBLISHED,
            test_content="回调联调",
            environment="联调A",
        )
        _add_daily(
            db,
            action=a,
            user_id=xj,
            report_date=today,
            progress=20,
            risk="对端 Mock 502",
            note="已拉研发",
            is_blocking=True,
        )
        a = _mk_action(
            db,
            task=t_agent,
            title="【场景】本周-工具链阻塞",
            owner_id=zw,
            week_start=report_ws,
            status=STATUS_PUBLISHED,
            test_content="评测流水线",
            environment="CI",
        )
        _add_daily(
            db,
            action=a,
            user_id=zw,
            report_date=today,
            progress=10,
            risk="Runner 镜像拉取失败",
            note="等基建",
            is_blocking=True,
        )
        a = _mk_action(
            db,
            task=t_agent,
            title="【场景】本周-刚启动低进度",
            owner_id=hj,
            week_start=report_ws,
            status=STATUS_PUBLISHED,
            test_content="用例设计",
            environment="本地",
        )
        _add_daily(
            db, action=a, user_id=hj, report_date=today, progress=5, risk="", note="刚起步"
        )
        a = _mk_action(
            db,
            task=t_agent,
            title="【场景】本周-中进度无风险",
            owner_id=xj,
            week_start=report_ws,
            status=STATUS_PUBLISHED,
            test_content="Prompt 回归",
            environment="staging",
        )
        _add_daily(
            db, action=a, user_id=xj, report_date=today, progress=60, risk="", note="按计划"
        )
        a = _mk_action(
            db,
            task=t_agent,
            title="【场景】本周-高进度待收尾",
            owner_id=hj,
            week_start=report_ws,
            status=STATUS_PUBLISHED,
            test_content="报告整理",
            environment="—",
        )
        _add_daily(
            db, action=a, user_id=hj, report_date=today, progress=90, risk="", note="差结论页"
        )
        # 上周也挂一条在「新 Task」上不合适——新 Task 无上周；再给 Agent 放一个纯上周小 Task 便于切换历史周
        t_agent_old = _find_or_create_task(
            db,
            project_id=proj.id,
            domain=domains["Agent"],
            title="【场景】自定义 Agent 上轮收尾（旧Task）",
            requirement="主要用于「上周」大屏切换演示。",
            lead_id=xj,
            tester_ids=[hj],
        )
        _purge_scenario_actions(db, t_agent_old.id)
        a = _mk_action(
            db,
            task=t_agent_old,
            title="【场景】上周-权限矩阵回归（已完成）",
            owner_id=xj,
            week_start=prev_ws,
            status=STATUS_DONE,
            test_content="权限用例",
            environment="staging",
        )
        _add_daily(
            db, action=a, user_id=xj, report_date=prev_mid, progress=100, risk="", note="上周完成"
        )
        a = _mk_action(
            db,
            task=t_agent_old,
            title="【场景】上周-Skill 编排阻塞",
            owner_id=hj,
            week_start=prev_ws,
            status=STATUS_PUBLISHED,
            test_content="编排链路",
            environment="staging",
        )
        _add_daily(
            db,
            action=a,
            user_id=hj,
            report_date=prev_mid,
            progress=55,
            risk="编排超时未复现稳定",
            note="上周遗留风险",
        )
        # 旧 Task 本周继续：便于凑满本周大屏 Task 数
        a = _mk_action(
            db,
            task=t_agent_old,
            title="【场景】本周-上轮遗留复测",
            owner_id=xj,
            week_start=report_ws,
            status=STATUS_PUBLISHED,
            test_content="复测编排",
            environment="staging",
        )
        _add_daily(
            db,
            action=a,
            user_id=xj,
            report_date=today,
            progress=40,
            risk="",
            note="复测中",
        )

        # ── 交付 ──
        t_deliv = _find_or_create_task(
            db,
            project_id=proj.id,
            domain=domains["交付"],
            title="【场景】0507 安装包验证（跨周）",
            requirement="交付域场景：上周完成 + 本周新风险。",
            lead_id=zw,
            tester_ids=[hj],
        )
        _purge_scenario_actions(db, t_deliv.id)
        a = _mk_action(
            db,
            task=t_deliv,
            title="【场景】上周-ARM 包安装（已完成）",
            owner_id=zw,
            week_start=prev_ws,
            status=STATUS_DONE,
            test_content="ARM 安装",
            environment="交付机房",
        )
        _add_daily(
            db, action=a, user_id=zw, report_date=prev_mid, progress=100, risk="", note="安装通过"
        )
        a = _mk_action(
            db,
            task=t_deliv,
            title="【场景】本周-升级回滚演练（有风险）",
            owner_id=hj,
            week_start=report_ws,
            status=STATUS_PUBLISHED,
            test_content="升级回滚",
            environment="交付机房",
        )
        _add_daily(
            db,
            action=a,
            user_id=hj,
            report_date=today,
            progress=30,
            risk="回滚脚本缺权限",
            note="待运维开通",
            is_blocking=True,
        )

        # ── 定制 ──
        t_cust = _find_or_create_task(
            db,
            project_id=proj.id,
            domain=domains["定制"],
            title="【场景】客户定制联调（跨周）",
            requirement="定制域：上周有进展，本周推进良好无风险。",
            lead_id=xj,
            tester_ids=[zw],
        )
        _purge_scenario_actions(db, t_cust.id)
        a = _mk_action(
            db,
            task=t_cust,
            title="【场景】上周-需求澄清会",
            owner_id=xj,
            week_start=prev_ws,
            status=STATUS_DONE,
            test_content="澄清会",
            environment="—",
        )
        _add_daily(
            db, action=a, user_id=xj, report_date=prev_mid, progress=100, risk="", note="纪要已出"
        )
        a = _mk_action(
            db,
            task=t_cust,
            title="【场景】本周-联调推进无风险",
            owner_id=zw,
            week_start=report_ws,
            status=STATUS_PUBLISHED,
            test_content="联调",
            environment="客户 UAT",
        )
        _add_daily(
            db, action=a, user_id=zw, report_date=today, progress=65, risk="", note="按计划推进"
        )
        db.add(
            TmActionCorrection(
                action_id=a.id, user_id=zw, note="更正：环境为客户 UAT，非内网 staging"
            )
        )

        # Task 已完成（本汇报周有 Action，Task 自身 done → 大屏「已完成」）
        t_done = _find_or_create_task(
            db,
            project_id=proj.id,
            domain=domains["平台"],
            title="【场景】文档走查专项（Task已完成）",
            requirement="验证「已完成」Tab 仅 Task 维度。",
            lead_id=zw,
            tester_ids=[],
            status=TASK_STATUS_DONE,
        )
        _purge_scenario_actions(db, t_done.id)
        a = _mk_action(
            db,
            task=t_done,
            title="【场景】本周-走查完成",
            owner_id=zw,
            week_start=report_ws,
            status=STATUS_DONE,
            test_content="走查",
            environment="—",
        )
        _add_daily(
            db, action=a, user_id=zw, report_date=today, progress=100, risk="", note="走查完成"
        )

        # ── 补齐至 13 个本周可见【场景】Task，并覆盖手填周进度 ──
        report_wk = period.week_key

        t_manual_high = _find_or_create_task(
            db,
            project_id=proj.id,
            domain=domains["平台"],
            title="【场景】手填偏高（Action低/手填90）",
            requirement="Action 平均偏低，但 lead 手填 90%，验证手填优先。",
            lead_id=hj,
            tester_ids=[xj],
        )
        _purge_scenario_actions(db, t_manual_high.id)
        a = _mk_action(
            db,
            task=t_manual_high,
            title="【场景】本周-手填偏高-慢推进",
            owner_id=xj,
            week_start=report_ws,
            status=STATUS_PUBLISHED,
            test_content="文档对齐",
            environment="—",
        )
        _add_daily(
            db, action=a, user_id=xj, report_date=today, progress=20, risk="", note="文档卡住"
        )
        _upsert_week_progress(
            db,
            task_id=t_manual_high.id,
            week_key_s=report_wk,
            progress=90,
            note="整体方案已评审，手填偏高",
            updated_by=hj,
        )

        t_manual_low = _find_or_create_task(
            db,
            project_id=proj.id,
            domain=domains["Agent"],
            title="【场景】手填偏低（Action高/手填25）",
            requirement="Action 已较高，但 lead 手填 25%，验证手填优先与风险观感。",
            lead_id=xj,
            tester_ids=[hj, zw],
        )
        _purge_scenario_actions(db, t_manual_low.id)
        for title, owner, prog in (
            ("【场景】本周-手填偏低-A", hj, 80),
            ("【场景】本周-手填偏低-B", zw, 75),
        ):
            a = _mk_action(
                db,
                task=t_manual_low,
                title=title,
                owner_id=owner,
                week_start=report_ws,
                status=STATUS_PUBLISHED,
                test_content="联调",
                environment="staging",
            )
            _add_daily(
                db, action=a, user_id=owner, report_date=today, progress=prog, risk="", note="单点完成度高"
            )
        _upsert_week_progress(
            db,
            task_id=t_manual_low.id,
            week_key_s=report_wk,
            progress=25,
            note="主链路未通，手填偏低",
            updated_by=xj,
        )

        t_secure = _find_or_create_task(
            db,
            project_id=proj.id,
            domain=domains["平台"],
            title="【场景】安全扫描专项（多Action无阻塞）",
            requirement="多 Action、无阻塞、未手填（对照手填项）。",
            lead_id=zw,
            tester_ids=[hj, xj],
        )
        _purge_scenario_actions(db, t_secure.id)
        for title, owner, prog in (
            ("【场景】本周-依赖漏洞扫描", hj, 55),
            ("【场景】本周-权限边界用例", xj, 40),
            ("【场景】本周-审计日志抽检", zw, 70),
        ):
            a = _mk_action(
                db,
                task=t_secure,
                title=title,
                owner_id=owner,
                week_start=report_ws,
                status=STATUS_PUBLISHED,
                test_content="安全",
                environment="staging",
            )
            _add_daily(
                db, action=a, user_id=owner, report_date=today, progress=prog, risk="", note="推进中"
            )

        t_gray = _find_or_create_task(
            db,
            project_id=proj.id,
            domain=domains["交付"],
            title="【场景】灰度放量观察（阻塞+手填）",
            requirement="单阻塞 + 手填 55%。",
            lead_id=zw,
            tester_ids=[hj],
        )
        _purge_scenario_actions(db, t_gray.id)
        a = _mk_action(
            db,
            task=t_gray,
            title="【场景】本周-灰度指标核对",
            owner_id=hj,
            week_start=report_ws,
            status=STATUS_PUBLISHED,
            test_content="灰度",
            environment="生产灰度",
        )
        _add_daily(
            db,
            action=a,
            user_id=hj,
            report_date=today,
            progress=35,
            risk="错误率阈值未达放量门槛",
            note="暂停扩量",
            is_blocking=True,
        )
        a = _mk_action(
            db,
            task=t_gray,
            title="【场景】本周-回滚预案演练",
            owner_id=zw,
            week_start=report_ws,
            status=STATUS_PUBLISHED,
            test_content="回滚",
            environment="生产灰度",
        )
        _add_daily(
            db, action=a, user_id=zw, report_date=today, progress=50, risk="", note="预案已过"
        )
        _upsert_week_progress(
            db,
            task_id=t_gray.id,
            week_key_s=report_wk,
            progress=55,
            note="阻塞未解，整体手填 55%",
            updated_by=zw,
        )

        t_monitor = _find_or_create_task(
            db,
            project_id=proj.id,
            domain=domains["定制"],
            title="【场景】监控大盘改造（未手填对照）",
            requirement="有进展但故意不手填周进度。",
            lead_id=xj,
            tester_ids=[zw],
        )
        _purge_scenario_actions(db, t_monitor.id)
        a = _mk_action(
            db,
            task=t_monitor,
            title="【场景】本周-大盘图表改造",
            owner_id=zw,
            week_start=report_ws,
            status=STATUS_PUBLISHED,
            test_content="图表",
            environment="UAT",
        )
        _add_daily(
            db, action=a, user_id=zw, report_date=today, progress=48, risk="", note="未手填对照"
        )

        t_arch = _find_or_create_task(
            db,
            project_id=proj.id,
            domain=domains["交付"],
            title="【场景】资源扩容评估（已归档）",
            requirement="归档 Task：验证「归档」筛选。",
            lead_id=hj,
            tester_ids=[zw],
            status=TASK_STATUS_CANCELLED,
        )
        _purge_scenario_actions(db, t_arch.id)
        a = _mk_action(
            db,
            task=t_arch,
            title="【场景】本周-归档前遗留核对",
            owner_id=hj,
            week_start=report_ws,
            status=STATUS_DONE,
            test_content="核对",
            environment="—",
        )
        _add_daily(
            db, action=a, user_id=hj, report_date=today, progress=100, risk="", note="归档前收尾"
        )
        _upsert_week_progress(
            db,
            task_id=t_arch.id,
            week_key_s=report_wk,
            progress=100,
            note="归档收尾手填 100%",
            updated_by=hj,
        )

        t_miss = _find_or_create_task(
            db,
            project_id=proj.id,
            domain=domains["Agent"],
            title="【场景】本周新建仅未日更集中",
            requirement="两条进行中均未今日日更。",
            lead_id=xj,
            tester_ids=[hj, zw],
        )
        _purge_scenario_actions(db, t_miss.id)
        for title, owner, prog in (
            ("【场景】本周-未日更-用例编写", hj, 30),
            ("【场景】本周-未日更-数据准备", zw, 15),
        ):
            a = _mk_action(
                db,
                task=t_miss,
                title=title,
                owner_id=owner,
                week_start=report_ws,
                status=STATUS_PUBLISHED,
                test_content="准备",
                environment="本地",
            )
            _add_daily(
                db,
                action=a,
                user_id=owner,
                report_date=today - timedelta(days=1),
                progress=prog,
                risk="",
                note="昨日有写，今日未更",
            )

        # 已有主 Task 也补手填：平台 / Agent 联调 / 定制
        _upsert_week_progress(
            db,
            task_id=t_plat.id,
            week_key_s=report_wk,
            progress=58,
            note="平台主线手填 58%（含双阻塞）",
            updated_by=hj,
        )
        _upsert_week_progress(
            db,
            task_id=t_agent.id,
            week_key_s=report_wk,
            progress=42,
            note="Agent 联调手填 42%",
            updated_by=xj,
        )
        _upsert_week_progress(
            db,
            task_id=t_cust.id,
            week_key_s=report_wk,
            progress=70,
            note="定制联调手填 70%",
            updated_by=xj,
        )
        _upsert_week_progress(
            db,
            task_id=t_done.id,
            week_key_s=report_wk,
            progress=100,
            note="已完成 Task 手填 100%",
            updated_by=zw,
        )

        # 强制对齐看板活动周键（避免 week_key(week_start) 与 period.week_key 漂移）
        n_fix = (
            db.query(TmAction)
            .filter(TmAction.title.like("【场景】本周%"))
            .update(
                {
                    TmAction.week_key: report_wk,
                    TmAction.week_start: report_ws,
                    TmAction.due_at: period.week_end,
                },
                synchronize_session=False,
            )
        )
        print(f"  aligned 【场景】本周* actions -> {report_wk} count={n_fix}")

        db.commit()
        print(f"  project={PROJECT_NAME} domains={list(DOMAIN_NAMES)}")
        scenario_tasks = (
            db.query(TmTask)
            .filter(TmTask.project_id == proj.id, TmTask.title.like("【场景】%"))
            .all()
        )
        # 本周至少有一条非草稿 Action 的 Task
        week_task_ids = {
            a.task_id
            for a in db.query(TmAction)
            .filter(
                TmAction.week_key == report_wk,
                TmAction.title.like("【场景】%"),
                TmAction.status != STATUS_DRAFT,
            )
            .all()
        }
        n_week_tasks = len([t for t in scenario_tasks if t.id in week_task_ids])
        n_manual = (
            db.query(TmTaskWeekProgress)
            .filter(
                TmTaskWeekProgress.week_key == report_wk,
                TmTaskWeekProgress.task_id.in_([t.id for t in scenario_tasks]),
            )
            .count()
        )
        print(f"  scenario tasks total={len(scenario_tasks)} with_this_week_actions={n_week_tasks}")
        print(f"  manual week_progress rows={n_manual}")
        print("  tip: 大屏切换「本周/上周」可看历史周 Action；手填进度看「未手填」提示消失")
        print("== done ==")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
