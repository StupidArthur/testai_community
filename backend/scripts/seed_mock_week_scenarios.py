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
    STATUS_CANCELLED,
    STATUS_DONE,
    STATUS_DRAFT,
    STATUS_PUBLISHED,
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
)
from app.test_manage.week import (
    current_week_start,
    daily_context_week_start,
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
) -> TmAction:
    a = TmAction(
        task_id=task.id,
        project_id=task.project_id,
        domain_id=task.domain_id,
        week_start=week_start,
        week_key=week_key(week_start),
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
) -> None:
    db.add(
        TmDailyUpdate(
            action_id=action.id,
            user_id=user_id,
            report_date=report_date,
            progress_percent=progress,
            risk_blocker=risk,
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

        report_ws = daily_context_week_start()
        prev_ws = previous_week_start(report_ws)
        today = now_tm().date()
        prev_mid = (prev_ws + timedelta(days=3)).date()
        print(f"  report_week={week_key(report_ws)} prev_week={week_key(prev_ws)} today={today}")

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
            title="【场景】本周-进行中有风险",
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
            requirement="本周新建，无上周 Action。",
            lead_id=xj,
            tester_ids=[hj],
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

        db.commit()
        print(f"  project={PROJECT_NAME} domains={list(DOMAIN_NAMES)}")
        print("  tip: 大屏切换「本周/上周」可看历史周 Action")
        print("== done ==")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
