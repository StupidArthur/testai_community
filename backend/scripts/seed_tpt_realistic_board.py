"""
TPT v2.1 看板 / 需求大屏演示数据。

覆盖需求进展六阶段，Task 总量约 20；「测试中」保留少量 Action 场景（风险、未日更、空卡等）。
周归属对齐库内活动周（get_or_create_active_period）。

用法（在 backend 目录）：

    python scripts/seed_tpt_realistic_board.py

每次运行会清空「TPT v2.1」下旧 Task/Action/日更/周进度/推送快照后重建。
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
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
    REQ_STAGE_DEVELOPING,
    REQ_STAGE_PENDING_DEV,
    REQ_STAGE_PENDING_HANDOVER,
    REQ_STAGE_PENDING_TEST,
    REQ_STAGE_TEST_DONE,
    REQ_STAGE_TESTING,
    STATUS_DONE,
    STATUS_DRAFT,
    STATUS_PUBLISHED,
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
    TmTaskUpdateLog,
    TmTaskWeekProgress,
    TmWeekPeriod,
)
from app.test_manage.period import get_or_create_active_period
from app.test_manage.req_stage import sync_test_status_for_stage

PROJECT_NAME = "TPT v2.1"
DEFAULT_PASSWORD = "123456"
DOMAIN_NAMES = ("平台", "Agent", "交付", "定制")

# 目标 Task 总量（六阶段合计）
TARGET_TASK_COUNT = 20

# 中文名 → 登录名
NAME_TO_USER = {
    "黄婧": "hj",
    "袁小君": "xiaojun",
    "张莹": "zhangying",
    "张雯": "zhangwen",
    "尤佳欣": "youjiaxin",
    "刘洁": "liujie",
    "叶学武": "yexuewu",
    "丁乔": "dingqiao",
    "袁琦": "yuanqi",
    "徐文耀": "xuwenyao",
    "孙厚凯": "sunhoukai",
    "童霜": "tongshuang",
    "刘灏": "liuhao",
}


def _ensure_user(db: Session, username: str, real_name: str) -> User:
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
    return row


def _wipe_project_tree(db: Session, project: TmProject) -> None:
    tasks = db.query(TmTask).filter(TmTask.project_id == project.id).all()
    tids = [t.id for t in tasks]
    actions = db.query(TmAction).filter(TmAction.project_id == project.id).all()
    aids = [a.id for a in actions]
    if aids:
        db.query(TmDailyUpdate).filter(TmDailyUpdate.action_id.in_(aids)).delete(
            synchronize_session=False
        )
        db.query(TmActionCorrection).filter(TmActionCorrection.action_id.in_(aids)).delete(
            synchronize_session=False
        )
        db.query(TmAction).filter(TmAction.id.in_(aids)).update(
            {TmAction.source_action_id: None}, synchronize_session=False
        )
        db.query(TmAction).filter(TmAction.id.in_(aids)).delete(synchronize_session=False)
    if tids:
        db.query(TmTaskWeekProgress).filter(TmTaskWeekProgress.task_id.in_(tids)).delete(
            synchronize_session=False
        )
        db.query(TmTaskUpdateLog).filter(TmTaskUpdateLog.task_id.in_(tids)).delete(
            synchronize_session=False
        )
        db.query(TmTaskTester).filter(TmTaskTester.task_id.in_(tids)).delete(
            synchronize_session=False
        )
        db.query(TmTask).filter(TmTask.id.in_(tids)).delete(synchronize_session=False)
    snap_n = db.query(TmPushSnapshot).delete(synchronize_session=False)
    run_n = db.query(TmPushRun).delete(synchronize_session=False)
    print(f"  wiped tasks={len(tids)} actions={len(aids)} snaps={snap_n} runs={run_n}")


def _ensure_domains(db: Session, project_id: str) -> dict[str, TmDomain]:
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
        out[name] = d
    return out


def _mk_task(
    db: Session,
    *,
    project: TmProject,
    domain: TmDomain,
    title: str,
    requirement: str,
    lead: User,
    testers: list[User],
    creator: User,
    req_stage: str,
    expected_handover_at: date | None = None,
    actual_handover_at: date | None = None,
    test_started_at: date | None = None,
    expected_test_end_at: date | None = None,
    test_ended_at: date | None = None,
) -> TmTask:
    """按需求进展建 Task；测试状态随阶段联动。"""
    synced = sync_test_status_for_stage(req_stage)
    status = synced or TASK_STATUS_PUBLISHED
    task = TmTask(
        project_id=project.id,
        domain_id=domain.id,
        title=title,
        requirement=requirement,
        lead_id=lead.id,
        status=status,
        req_stage=req_stage,
        expected_handover_at=expected_handover_at,
        actual_handover_at=actual_handover_at,
        test_started_at=test_started_at,
        expected_test_end_at=expected_test_end_at,
        test_ended_at=test_ended_at,
        created_by=creator.id,
        published_at=now_tm() if status == TASK_STATUS_PUBLISHED else None,
    )
    db.add(task)
    db.flush()
    for u in testers:
        if u.id != lead.id:
            db.add(TmTaskTester(task_id=task.id, user_id=u.id))
    db.add(
        TmTaskUpdateLog(
            task_id=task.id,
            user_id=creator.id,
            summary="演示灌数：需求进展六阶段",
            detail="seed_tpt_realistic_board",
        )
    )
    return task


def _mk_action(
    db: Session,
    *,
    task: TmTask,
    period: TmWeekPeriod,
    title: str,
    owner: User,
    creator: User,
    status: str,
    test_content: str = "",
    environment: str = "qa",
    source_action_id: str | None = None,
) -> TmAction:
    a = TmAction(
        task_id=task.id,
        project_id=task.project_id,
        domain_id=task.domain_id,
        week_start=period.week_start,
        week_key=period.week_key,
        title=title,
        owner_id=owner.id,
        test_content=test_content[:1000],
        environment=environment[:300],
        status=status,
        created_by=creator.id,
        published_at=now_tm() if status not in (STATUS_DRAFT,) else None,
        due_at=period.week_end,
        source_action_id=source_action_id,
    )
    db.add(a)
    db.flush()
    return a


def _add_daily(
    db: Session,
    *,
    action: TmAction,
    owner: User,
    report_date: date,
    progress: int,
    note: str,
    risk: str = "",
    is_blocking: bool = False,
) -> None:
    db.add(
        TmDailyUpdate(
            action_id=action.id,
            user_id=owner.id,
            report_date=report_date,
            progress_percent=max(0, min(100, progress)),
            risk_blocker=(risk or "")[:1000],
            progress_note=(note or "")[:1000],
            is_blocking=bool(is_blocking and (risk or "").strip()),
        )
    )


def _prev_period(db: Session, active: TmWeekPeriod) -> TmWeekPeriod | None:
    return (
        db.query(TmWeekPeriod)
        .filter(TmWeekPeriod.week_end <= active.week_start)
        .order_by(TmWeekPeriod.week_end.desc())
        .first()
    )


def _ensure_prev_period(db: Session, active: TmWeekPeriod, user_id: int) -> TmWeekPeriod:
    """若库中尚无上一周周期，补一条紧挨活动周的历史周。"""
    prev = _prev_period(db, active)
    if prev:
        return prev
    span = active.week_end - active.week_start
    prev_end = active.week_start
    prev_start = prev_end - span
    from app.test_manage.week import week_key as wk

    key = wk(prev_start)
    prev = TmWeekPeriod(
        week_key=key,
        week_start=prev_start,
        week_end=prev_end,
        created_by=user_id,
    )
    db.add(prev)
    db.flush()
    print(f"  + prev week_period {prev.week_key}")
    return prev


def seed_tpt_realistic_board() -> None:
    db = SessionLocal()
    try:
        print("== seed TPT realistic board (req stages ~20 tasks) ==")
        admin = db.query(User).filter(User.username == "admin").first()
        if not admin:
            admin = db.query(User).filter(User.username == "manager").first()
        if not admin:
            admin = _ensure_user(db, "manager", "管理员")
            admin.role = UserRole.Admin
            db.flush()

        users: dict[str, User] = {}
        for cn, uname in NAME_TO_USER.items():
            users[cn] = _ensure_user(db, uname, cn)
        db.commit()

        active = get_or_create_active_period(db, user_id=admin.id)
        prev = _ensure_prev_period(db, active, admin.id)
        today = now_tm().date()
        prev_day = min(today, (prev.week_end - timedelta(hours=1)).date())
        cur_day = min(today, max(active.week_start.date(), today))
        print(f"  active={active.week_key} prev={prev.week_key} today={today}")

        proj = db.query(TmProject).filter(TmProject.name == PROJECT_NAME).first()
        if not proj:
            proj = TmProject(
                name=PROJECT_NAME,
                description="TPT 测试计划演示项目（需求进展六阶段）",
                status=PROJECT_STATUS_ACTIVE,
                created_by=admin.id,
            )
            db.add(proj)
            db.flush()
            print(f"  + project {PROJECT_NAME}")
        else:
            _wipe_project_tree(db, proj)

        domains = _ensure_domains(db, proj.id)
        U = users
        n = 0

        # ── 待开发 ×2 ──────────────────────────────────────────────────
        for title, domain, lead, testers, req in [
            (
                "【待开发】知识库检索二期立项",
                "平台",
                U["黄婧"],
                [U["尤佳欣"]],
                "需求评审中，尚未排期开发",
            ),
            (
                "【待开发】客户报表导出评估",
                "定制",
                U["张雯"],
                [],
                "商务评估包，待排入迭代",
            ),
        ]:
            _mk_task(
                db,
                project=proj,
                domain=domains[domain],
                title=title,
                requirement=req,
                lead=lead,
                testers=testers,
                creator=admin,
                req_stage=REQ_STAGE_PENDING_DEV,
            )
            n += 1

        # ── 开发中 ×3 ──────────────────────────────────────────────────
        for title, domain, lead, testers, req in [
            (
                "【开发中】Agent 条件触发引擎",
                "Agent",
                U["袁小君"],
                [U["徐文耀"]],
                "研发联调中，预计下周提测",
            ),
            (
                "【开发中】HMI 流程库改版",
                "平台",
                U["叶学武"],
                [U["丁乔"]],
                "前端改版 60%，接口未合入",
            ),
            (
                "【开发中】多架构安装包打包",
                "交付",
                U["张雯"],
                [U["黄婧"]],
                "ARM/x86 打包脚本开发中",
            ),
        ]:
            _mk_task(
                db,
                project=proj,
                domain=domains[domain],
                title=title,
                requirement=req,
                lead=lead,
                testers=testers,
                creator=admin,
                req_stage=REQ_STAGE_DEVELOPING,
            )
            n += 1

        # ── 待提测 ×3（必填预计提测）──────────────────────────────────
        for title, domain, lead, testers, days, req in [
            (
                "【待提测】问数评估包",
                "平台",
                U["丁乔"],
                [U["张莹"]],
                3,
                "研发自测中，预计提测见节点时间",
            ),
            (
                "【待提测】报警管理 Agents",
                "Agent",
                U["孙厚凯"],
                [U["袁小君"]],
                5,
                "模型侧收尾，排队提测",
            ),
            (
                "【待提测】升级回滚脚本",
                "交付",
                U["黄婧"],
                [U["张雯"]],
                2,
                "脚本评审后提测",
            ),
        ]:
            _mk_task(
                db,
                project=proj,
                domain=domains[domain],
                title=title,
                requirement=req,
                lead=lead,
                testers=testers,
                creator=admin,
                req_stage=REQ_STAGE_PENDING_HANDOVER,
                expected_handover_at=today + timedelta(days=days),
            )
            n += 1

        # ── 待测试 ×3（已提测、等人）──────────────────────────────────
        for title, domain, lead, testers, ago, req in [
            (
                "【待测试】数据中心增强",
                "平台",
                U["袁琦"],
                [U["黄婧"]],
                1,
                "已提测，测试资源排队中",
            ),
            (
                "【待测试】设备健康 Agent",
                "Agent",
                U["徐文耀"],
                [U["袁小君"]],
                2,
                "环境已就绪，待排测试人员",
            ),
            (
                "【待测试】客户 UAT 清单首批",
                "定制",
                U["张莹"],
                [U["张雯"]],
                0,
                "今日刚提测，待排期开测",
            ),
        ]:
            _mk_task(
                db,
                project=proj,
                domain=domains[domain],
                title=title,
                requirement=req,
                lead=lead,
                testers=testers,
                creator=admin,
                req_stage=REQ_STAGE_PENDING_TEST,
                actual_handover_at=today - timedelta(days=ago),
                expected_handover_at=today - timedelta(days=ago + 2),
            )
            n += 1

        # ── 测试中 ×6（含 Action / 风险 / 未日更 / 空卡 / 草稿）────────
        # 1) Agent 主线：跨周延续 + 风险 + 草稿
        t_agent = _mk_task(
            db,
            project=proj,
            domain=domains["Agent"],
            title="【测试中】Agent 平台能力",
            requirement="自定义 Agent / Skill / 应用关联 / 报表接口",
            lead=U["袁小君"],
            testers=[U["黄婧"], U["尤佳欣"], U["刘洁"]],
            creator=admin,
            req_stage=REQ_STAGE_TESTING,
            test_started_at=today - timedelta(days=5),
            expected_test_end_at=today + timedelta(days=4),
        )
        n += 1
        a_prev_custom = _mk_action(
            db,
            task=t_agent,
            period=prev,
            title="自定义Agent",
            owner=U["袁小君"],
            creator=admin,
            status=STATUS_PUBLISHED,
            test_content="上周遗留 bug 回归",
            environment="staging",
        )
        _add_daily(
            db,
            action=a_prev_custom,
            owner=U["袁小君"],
            report_date=prev_day,
            progress=80,
            note="上周阶段完成",
            risk="遗留 8 个 bug",
            is_blocking=True,
        )
        a_cur_custom = _mk_action(
            db,
            task=t_agent,
            period=active,
            title="自定义Agent",
            owner=U["袁小君"],
            creator=admin,
            status=STATUS_PUBLISHED,
            test_content="本周条件触发与遗留 bug",
            environment="staging",
            source_action_id=a_prev_custom.id,
        )
        _add_daily(
            db,
            action=a_cur_custom,
            owner=U["袁小君"],
            report_date=cur_day,
            progress=72,
            note="条件触发联调中",
            risk="条件触发偶发不触发",
            is_blocking=True,
        )
        _mk_action(
            db,
            task=t_agent,
            period=active,
            title="应用关联自主Agent",
            owner=U["袁小君"],
            creator=admin,
            status=STATUS_DRAFT,
            test_content="待发布",
            environment="",
        )
        a_report = _mk_action(
            db,
            task=t_agent,
            period=active,
            title="统计报表Agent接口",
            owner=U["尤佳欣"],
            creator=admin,
            status=STATUS_PUBLISHED,
            test_content="自定义明细",
            environment="qa",
        )
        _add_daily(
            db,
            action=a_report,
            owner=U["尤佳欣"],
            report_date=cur_day,
            progress=55,
            note="字段对齐中",
        )
        db.add(
            TmTaskWeekProgress(
                task_id=t_agent.id,
                week_key=active.week_key,
                progress_percent=68,
                note="手填周进度演示",
                updated_by=U["袁小君"].id,
            )
        )

        # 2) 业务 Agents：多 owner + 阻塞
        t_biz = _mk_task(
            db,
            project=proj,
            domain=domains["Agent"],
            title="【测试中】业务 Agents 专项",
            requirement="设备健康 / 报警 / 操作导引 / 智能控制",
            lead=U["袁小君"],
            testers=[U["徐文耀"], U["孙厚凯"], U["童霜"], U["刘灏"]],
            creator=admin,
            req_stage=REQ_STAGE_TESTING,
            test_started_at=today - timedelta(days=4),
            expected_test_end_at=today + timedelta(days=3),
        )
        n += 1
        for title, owner, prog, risk, note, blocking in [
            ("设备健康agent", U["徐文耀"], 90, "data-hub 未上送", "链路不稳", True),
            ("操作导引Agents", U["童霜"], 80, "数据读写阻塞", "UI 已测", True),
            ("智能控制融合", U["刘灏"], 80, "", "脚本推进中", False),
        ]:
            a = _mk_action(
                db,
                task=t_biz,
                period=active,
                title=title,
                owner=owner,
                creator=admin,
                status=STATUS_PUBLISHED,
                test_content=title,
                environment="qa-45",
            )
            _add_daily(
                db,
                action=a,
                owner=owner,
                report_date=cur_day,
                progress=prog,
                note=note,
                risk=risk,
                is_blocking=blocking,
            )

        # 3) 平台 AI：完成项 + 阻塞 + 更正
        t_llm = _mk_task(
            db,
            project=proj,
            domain=domains["平台"],
            title="【测试中】平台 AI / LLM",
            requirement="记忆 / 多 Agent / 边云协同",
            lead=U["黄婧"],
            testers=[U["袁琦"]],
            creator=admin,
            req_stage=REQ_STAGE_TESTING,
            test_started_at=today - timedelta(days=6),
            expected_test_end_at=today + timedelta(days=2),
        )
        n += 1
        a_llm_done = _mk_action(
            db,
            task=t_llm,
            period=active,
            title="LLM功能",
            owner=U["黄婧"],
            creator=admin,
            status=STATUS_DONE,
            test_content="记忆与 multi-agent",
        )
        _add_daily(
            db,
            action=a_llm_done,
            owner=U["黄婧"],
            report_date=cur_day,
            progress=100,
            note="LLM 测完",
        )
        a_pride = _mk_action(
            db,
            task=t_llm,
            period=active,
            title="数据中心增强联调",
            owner=U["袁琦"],
            creator=admin,
            status=STATUS_PUBLISHED,
            test_content="PRIDE 对接",
        )
        _add_daily(
            db,
            action=a_pride,
            owner=U["袁琦"],
            report_date=cur_day,
            progress=70,
            note="约 70%",
            risk="PRIDE 对接异常",
            is_blocking=True,
        )
        db.add(
            TmActionCorrection(
                action_id=a_pride.id,
                user_id=U["黄婧"].id,
                note="更正：阻塞归因为鉴权配置",
            )
        )

        # 4) 数据与控制：未日更（故意不写今日日更）+ 未手填周进度
        t_data = _mk_task(
            db,
            project=proj,
            domain=domains["平台"],
            title="【测试中】平台数据与控制",
            requirement="下写 / OPCUA / 问数",
            lead=U["叶学武"],
            testers=[U["丁乔"], U["张莹"]],
            creator=admin,
            req_stage=REQ_STAGE_TESTING,
            test_started_at=today - timedelta(days=3),
            expected_test_end_at=today + timedelta(days=5),
        )
        n += 1
        # 故意不写今日日更 → 「今日未日更」
        _mk_action(
            db,
            task=t_data,
            period=active,
            title="下写功能测试",
            owner=U["叶学武"],
            creator=admin,
            status=STATUS_PUBLISHED,
            test_content="数据下写",
        )
        a_ask = _mk_action(
            db,
            task=t_data,
            period=active,
            title="问数功能回归",
            owner=U["丁乔"],
            creator=admin,
            status=STATUS_PUBLISHED,
            test_content="pride/apc 接入",
        )
        _add_daily(
            db,
            action=a_ask,
            owner=U["丁乔"],
            report_date=cur_day,
            progress=80,
            note="direct 一轮完成",
        )

        # 5) 空 Task：本周 0 Action（工作台标红）
        _mk_task(
            db,
            project=proj,
            domain=domains["Agent"],
            title="【测试中】Skill 编排二期（空卡）",
            requirement="切周后尚未建本周 Action，用于空 Task 标红",
            lead=U["黄婧"],
            testers=[U["尤佳欣"]],
            creator=admin,
            req_stage=REQ_STAGE_TESTING,
            test_started_at=today - timedelta(days=1),
            expected_test_end_at=today + timedelta(days=6),
        )
        n += 1

        # 6) 仅草稿 Action（大屏默认隐藏草稿）
        t_draft = _mk_task(
            db,
            project=proj,
            domain=domains["定制"],
            title="【测试中】评估需求包（仅草稿）",
            requirement="本周仅有草稿 Action",
            lead=U["尤佳欣"],
            testers=[U["张莹"]],
            creator=admin,
            req_stage=REQ_STAGE_TESTING,
            test_started_at=today - timedelta(days=2),
            expected_test_end_at=today + timedelta(days=7),
        )
        n += 1
        _mk_action(
            db,
            task=t_draft,
            period=active,
            title="评估需求用例起草",
            owner=U["尤佳欣"],
            creator=admin,
            status=STATUS_DRAFT,
            test_content="待评审后发布",
            environment="",
        )

        # ── 测试完成 ×3 ────────────────────────────────────────────────
        for title, domain, lead, testers, ended_ago, req in [
            (
                "【测试完成】文档与用例走查",
                "平台",
                U["张雯"],
                [],
                1,
                "走查纪要已归档",
            ),
            (
                "【测试完成】数据查询三期",
                "平台",
                U["张莹"],
                [U["丁乔"]],
                3,
                "版本已部署",
            ),
            (
                "【测试完成】ARM 安装包验证",
                "交付",
                U["张雯"],
                [U["黄婧"]],
                5,
                "安装通过并关闭",
            ),
        ]:
            t_done = _mk_task(
                db,
                project=proj,
                domain=domains[domain],
                title=title,
                requirement=req,
                lead=lead,
                testers=testers,
                creator=admin,
                req_stage=REQ_STAGE_TEST_DONE,
                test_started_at=today - timedelta(days=ended_ago + 10),
                expected_test_end_at=today - timedelta(days=ended_ago + 1),
                test_ended_at=today - timedelta(days=ended_ago),
                actual_handover_at=today - timedelta(days=ended_ago + 12),
            )
            n += 1
            a_done = _mk_action(
                db,
                task=t_done,
                period=active,
                title=f"{title.replace('【测试完成】', '')}收尾",
                owner=lead,
                creator=admin,
                status=STATUS_DONE,
                test_content="归档",
            )
            _add_daily(
                db,
                action=a_done,
                owner=lead,
                report_date=cur_day,
                progress=100,
                note="测试完成",
            )

        db.commit()

        n_tasks = db.query(TmTask).filter(TmTask.project_id == proj.id).count()
        n_actions = db.query(TmAction).filter(TmAction.project_id == proj.id).count()
        from collections import Counter
        from app.test_manage.models import TmTask as _T

        stages = Counter(
            r[0]
            for r in db.query(_T.req_stage).filter(_T.project_id == proj.id).all()
        )
        print(f"== done: tasks={n_tasks} (built={n}, target≈{TARGET_TASK_COUNT}) actions={n_actions} ==")
        print("需求进展分布：")
        for code, label in [
            (REQ_STAGE_PENDING_DEV, "待开发"),
            (REQ_STAGE_DEVELOPING, "开发中"),
            (REQ_STAGE_PENDING_HANDOVER, "待提测"),
            (REQ_STAGE_PENDING_TEST, "待测试"),
            (REQ_STAGE_TESTING, "测试中"),
            (REQ_STAGE_TEST_DONE, "测试完成"),
        ]:
            print(f"  {label}: {stages.get(code, 0)}")
        print("测试中场景：跨周延续 / 阻塞 / 未日更 / 空卡 / 仅草稿 / 手填周进度")
        print("账号（密码 123456）: hj / zhangying / xiaojun / manager")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_tpt_realistic_board()
