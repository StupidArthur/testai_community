"""
TPT v2.3 产品包需求 seed：Excel SR → Project/Domain/Task + mock subtask/action。

数据来源：产品包需求 sheet 的系统需求 SR 行（需求维度 = Task）。
subtask 与 action 无真实数据，按 SR 描述行 mock；需求进展阶段按固定配比铺开，
其中「测试中」Task 带 Action 场景（完成/进行中/未日更/上周继承/草稿/风险）。

用法（在 backend 目录）：

    python scripts/seed_tpt_v23_package.py [Excel路径]

默认 Excel：C:\\Users\\huangjing4\\Documents\\TPT V2.3 产品包需求.xlsx
每次运行会清空「TPT v2.3 产品包」下旧 Task/Action/日更/周进度/推送快照后重建。
"""
from __future__ import annotations

import random
import sys
import uuid
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

from app.auth.models import User
from app.platform.database import SessionLocal
from app.test_manage.config import (
    PROJECT_STATUS_ACTIVE,
    REQ_STAGE_DEVELOPING,
    REQ_STAGE_PENDING_HANDOVER,
    REQ_STAGE_PENDING_TEST,
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

try:
    import openpyxl
except ImportError:  # pragma: no cover
    openpyxl = None

PROJECT_NAME = "TPT v2.3 产品包"
DEFAULT_EXCEL = r"C:\Users\huangjing4\Documents\TPT V2.3 产品包需求.xlsx"
SHEET_NAME = "产品包需求"

# 中文名 → 登录名（库内已有）
NAME_TO_USER = {
    "黄婧": "hj",
    "袁小君": "xiaojun",
    "叶学武": "yexuewu",
    "丁乔": "dingqiao",
    "袁琦": "yuanqi",
    "尤佳欣": "youjiaxin",
    "刘洁": "liujie",
    "张雯": "zhangwen",
    "徐文耀": "xuwenyao",
    "张莹": "zhangying",
    "孙厚凯": "sunhoukai",
    "童霜": "tongshuang",
    "刘灏": "liuhao",
    "刘佳": "liujia",
}
# 验证人不在库内时的兜底池
FALLBACK_POOL = ("hj", "xiaojun", "yexuewu", "yuanqi", "xuwenyao", "sunhoukai", "liujie", "zhangwen")
TESTER_POOL = ("youjiaxin", "liujie", "zhangying", "dingqiao", "tongshuang", "liuhao", "yuanqi")

# 需求进展铺开（合计须 ≤ SR 总数，剩余全部 developing）
STAGE_PLAN = [
    (REQ_STAGE_TESTING, 8),  # 带 Action 场景
    (REQ_STAGE_PENDING_TEST, 5),
    (REQ_STAGE_PENDING_HANDOVER, 7),
]
GENERIC_SUBTASKS = ("主流程功能验证", "边界与异常场景", "性能与稳定性")

rng = random.Random(20260826)


def _sid() -> str:
    return uuid.uuid4().hex[:12]


def _load_srs(path: Path) -> list[dict]:
    if openpyxl is None:
        raise SystemExit("缺少 openpyxl：pip install openpyxl")
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[SHEET_NAME]
    out: list[dict] = []
    for r in ws.iter_rows(min_row=4, values_only=True):
        sr_no, cat, sub, name, desc = r[4], r[6], r[7], r[8], r[9]
        if not sr_no or not name:
            continue
        out.append(
            {
                "no": str(sr_no).strip(),
                "cat": (str(cat).strip() if cat else "其他"),
                "sub": (str(sub).strip() if sub else ""),
                "name": str(name).strip(),
                "desc": (str(desc).strip() if desc else ""),
                "priority": (str(r[11]).strip() if r[11] else ""),
                "verifier": (str(r[15]).strip() if r[15] else ""),
            }
        )
    wb.close()
    return out


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
    db.query(TmPushSnapshot).delete(synchronize_session=False)
    db.query(TmPushRun).delete(synchronize_session=False)


def _mk_subtasks(sr: dict) -> list[dict]:
    """由 SR 描述行生成 subtask；不足则补通用项，2~5 个。"""
    lines = [ln.strip() for ln in sr["desc"].splitlines() if ln.strip()]
    rows: list[dict] = []
    seen: set[str] = set()
    for ln in lines[:5]:
        name = ln if len(ln) <= 20 else ln[:20]
        if name in seen:
            continue
        seen.add(name)
        rows.append({"sid": _sid(), "name": name, "content": ln, "deleted": False})
    for g in GENERIC_SUBTASKS:
        if len(rows) >= 2:
            break
        if g not in seen:
            seen.add(g)
            rows.append({"sid": _sid(), "name": g, "content": f"{sr['name']} · {g}", "deleted": False})
    return rows


def _mk_task(
    db: Session,
    *,
    project: TmProject,
    domain: TmDomain,
    sr: dict,
    subtasks: list[dict],
    lead: User,
    testers: list[User],
    creator: User,
    req_stage: str,
    today: date,
) -> TmTask:
    requirement = (
        f"[{sr['no']}]（{sr['sub'] or sr['cat']}｜优先级：{sr['priority'] or '中'}）\n{sr['desc']}"
    )
    kwargs: dict = {}
    if req_stage == REQ_STAGE_PENDING_HANDOVER:
        kwargs["expected_handover_at"] = today + timedelta(days=rng.randint(2, 6))
    elif req_stage == REQ_STAGE_PENDING_TEST:
        kwargs["actual_handover_at"] = today - timedelta(days=rng.randint(0, 2))
        kwargs["expected_handover_at"] = today - timedelta(days=rng.randint(2, 4))
    elif req_stage == REQ_STAGE_TESTING:
        kwargs["test_started_at"] = today - timedelta(days=rng.randint(2, 6))
        kwargs["expected_test_end_at"] = today + timedelta(days=rng.randint(2, 8))
    task = TmTask(
        project_id=project.id,
        domain_id=domain.id,
        title=sr["name"],
        requirement=requirement[:2000],
        subtasks=subtasks,
        lead_id=lead.id,
        status=sync_test_status_for_stage(req_stage) or TASK_STATUS_PUBLISHED,
        req_stage=req_stage,
        created_by=creator.id,
        published_at=now_tm(),
        **kwargs,
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
            summary="seed：TPT v2.3 产品包需求导入",
            detail="seed_tpt_v23_package",
        )
    )
    return task


def _mk_action(
    db: Session,
    *,
    task: TmTask,
    period: TmWeekPeriod,
    title: str,
    subtask_name: str,
    owner: User,
    creator: User,
    status: str,
    test_content: str = "",
    environment: str = "qa",
    source_action_id: str | None = None,
    initial_progress: int = 0,
) -> TmAction:
    a = TmAction(
        task_id=task.id,
        project_id=task.project_id,
        domain_id=task.domain_id,
        week_start=period.week_start,
        week_key=period.week_key,
        title=title[:200],
        subtask_name=subtask_name,
        owner_id=owner.id,
        test_content=test_content[:1000],
        environment=environment[:300],
        status=status,
        created_by=creator.id,
        published_at=now_tm() if status != STATUS_DRAFT else None,
        due_at=period.week_end,
        source_action_id=source_action_id,
        initial_progress=initial_progress,
    )
    db.add(a)
    db.flush()
    return a


def _daily(
    db: Session,
    *,
    action: TmAction,
    owner: User,
    report_date: date,
    progress: int,
    note: str,
    risk: str = "",
) -> None:
    db.add(
        TmDailyUpdate(
            action_id=action.id,
            user_id=owner.id,
            report_date=report_date,
            progress_percent=max(0, min(100, progress)),
            risk_blocker=(risk or "")[:1000],
            progress_note=(note or "")[:1000],
            is_blocking=bool(risk.strip()),
        )
    )


def _ensure_prev_period(db: Session, active: TmWeekPeriod, user_id: int) -> TmWeekPeriod:
    prev = (
        db.query(TmWeekPeriod)
        .filter(TmWeekPeriod.week_end <= active.week_start)
        .order_by(TmWeekPeriod.week_end.desc())
        .first()
    )
    if prev:
        return prev
    span = active.week_end - active.week_start
    prev_end = active.week_start
    prev_start = prev_end - span
    from app.test_manage.week import week_key as wk

    prev = TmWeekPeriod(week_key=wk(prev_start), week_start=prev_start, week_end=prev_end, created_by=user_id)
    db.add(prev)
    db.flush()
    return prev


def _seed_testing_actions(
    db: Session,
    *,
    task: TmTask,
    subtasks: list[dict],
    active: TmWeekPeriod,
    prev: TmWeekPeriod,
    owner: User,
    creator: User,
    cur_day: date,
    prev_day: date,
    idx: int,
) -> int:
    """测试中 Task 的 Action 场景；返回 action 数。"""
    n = 0
    env = rng.choice(("qa", "staging", "pre"))
    # 场景轮转：完成 / 进行中 / 未日更 / 上周继承 / 草稿
    mode = idx % 5
    st_done, st_run, st_nodaily, st_inherit, st_draft = range(5)

    if mode == st_inherit and len(subtasks) >= 1:
        name = subtasks[0]["name"]
        a_prev = _mk_action(
            db, task=task, period=prev, title=name, subtask_name=name,
            owner=owner, creator=creator, status=STATUS_DONE,
            test_content="上周执行未完成，本周延续", environment=env,
        )
        # 上周其实未完成（60%），本周继承：initial=60、当前进度继续
        a_prev.status = STATUS_PUBLISHED
        _daily(db, action=a_prev, owner=owner, report_date=prev_day, progress=60,
               note="上周推进到六成，剩余场景延续本周")
        a_cur = _mk_action(
            db, task=task, period=active, title=name, subtask_name=name,
            owner=owner, creator=creator, status=STATUS_PUBLISHED,
            test_content="延续上周剩余场景", environment=env,
            source_action_id=a_prev.id, initial_progress=60,
        )
        _daily(db, action=a_cur, owner=owner, report_date=cur_day, progress=85,
               note="剩余用例执行中", risk="环境偶发重启")
        n += 2
        if len(subtasks) >= 2:
            name2 = subtasks[1]["name"]
            a2 = _mk_action(
                db, task=task, period=active, title=name2, subtask_name=name2,
                owner=owner, creator=creator, status=STATUS_PUBLISHED,
                test_content=f"{name2} 用例执行", environment=env,
            )
            _daily(db, action=a2, owner=owner, report_date=cur_day, progress=40, note="用例执行中")
            n += 1
        return n

    for k, st in enumerate(subtasks[: rng.randint(2, 3)]):
        name = st["name"]
        if mode == st_done:
            a = _mk_action(
                db, task=task, period=active, title=name, subtask_name=name,
                owner=owner, creator=creator, status=STATUS_DONE,
                test_content=f"{name} 全量用例", environment=env,
            )
            _daily(db, action=a, owner=owner, report_date=cur_day, progress=100, note="全部通过，已交付")
        elif mode == st_run:
            a = _mk_action(
                db, task=task, period=active, title=name, subtask_name=name,
                owner=owner, creator=creator, status=STATUS_PUBLISHED,
                test_content=f"{name} 用例执行", environment=env,
            )
            _daily(
                db, action=a, owner=owner, report_date=cur_day,
                progress=rng.randint(30, 90), note="按计划推进",
                risk="偶现超时" if k == 0 else "",
            )
        elif mode == st_nodaily:
            a = _mk_action(
                db, task=task, period=active, title=name, subtask_name=name,
                owner=owner, creator=creator, status=STATUS_PUBLISHED,
                test_content=f"{name} 用例执行", environment=env,
            )
        else:  # st_draft：一个草稿 + 一个进行中
            if k == 0:
                _mk_action(
                    db, task=task, period=active, title=name, subtask_name=name,
                    owner=owner, creator=creator, status=STATUS_DRAFT,
                    test_content="待补充用例后发布", environment="",
                )
            else:
                a = _mk_action(
                    db, task=task, period=active, title=name, subtask_name=name,
                    owner=owner, creator=creator, status=STATUS_PUBLISHED,
                    test_content=f"{name} 冒烟验证", environment=env,
                )
                _daily(db, action=a, owner=owner, report_date=cur_day, progress=55, note="冒烟通过，详细执行中")
        n += 1
    return n


def main() -> None:
    excel = Path(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_EXCEL)
    srs = _load_srs(excel)
    if not srs:
        raise SystemExit(f"Excel 未解析到 SR 行：{excel}")
    print(f"== seed {PROJECT_NAME}：{len(srs)} SR ==")

    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.username == "admin").first() or db.query(
            User
        ).filter(User.username == "manager").first()
        users = {u.username: u for u in db.query(User).all()}

        active = get_or_create_active_period(db, user_id=admin.id)
        prev = _ensure_prev_period(db, active, admin.id)
        today = now_tm().date()
        cur_day = max(active.week_start.date(), today)
        prev_day = min(today, (prev.week_end - timedelta(hours=1)).date())
        print(f"  active={active.week_key} prev={prev.week_key}")

        proj = db.query(TmProject).filter(TmProject.name == PROJECT_NAME).first()
        if not proj:
            proj = TmProject(
                name=PROJECT_NAME,
                description="TPT v2.3 产品包需求（Excel SR 导入）",
                status=PROJECT_STATUS_ACTIVE,
                created_by=admin.id,
            )
            db.add(proj)
            db.flush()
            print(f"  + project {PROJECT_NAME}")
        else:
            _wipe_project_tree(db, proj)
            print("  wiped old tree")

        # 域 = 大类（按 SR 数量降序）
        cats = sorted({s["cat"] for s in srs})
        cat_count = {c: sum(1 for s in srs if s["cat"] == c) for c in cats}
        cats.sort(key=lambda c: -cat_count[c])
        domains: dict[str, TmDomain] = {}
        for i, c in enumerate(cats):
            d = (
                db.query(TmDomain)
                .filter(TmDomain.project_id == proj.id, TmDomain.name == c)
                .first()
            )
            if not d:
                d = TmDomain(project_id=proj.id, name=c, sort_order=i + 1)
                db.add(d)
                db.flush()
            domains[c] = d

        # 阶段分配：前 N 条进 plan（按大类分散），其余 developing
        stage_of: dict[int, str] = {}
        cursor = 0
        picked = set()
        for stage, cnt in STAGE_PLAN:
            for _ in range(cnt):
                # 轮询挑未分配行，保证大类分散
                while cursor < len(srs) and cursor in picked:
                    cursor += 1
                if cursor >= len(srs):
                    break
                stage_of[cursor] = stage
                picked.add(cursor)
                cursor += 1

        n_task = n_act = n_sub = 0
        for i, sr in enumerate(srs):
            stage = stage_of.get(i, REQ_STAGE_DEVELOPING)
            lead_uname = NAME_TO_USER.get(sr["verifier"]) or FALLBACK_POOL[i % len(FALLBACK_POOL)]
            lead = users[lead_uname]
            testers = [users[TESTER_POOL[(i + k) % len(TESTER_POOL)]] for k in range(2)]
            subtasks = _mk_subtasks(sr)
            task = _mk_task(
                db,
                project=proj,
                domain=domains[sr["cat"]],
                sr=sr,
                subtasks=subtasks,
                lead=lead,
                testers=testers,
                creator=admin,
                req_stage=stage,
                today=today,
            )
            n_task += 1
            n_sub += len(subtasks)
            if stage == REQ_STAGE_TESTING:
                owner = users[TESTER_POOL[i % len(TESTER_POOL)]]
                n_act += _seed_testing_actions(
                    db,
                    task=task,
                    subtasks=subtasks,
                    active=active,
                    prev=prev,
                    owner=owner,
                    creator=admin,
                    cur_day=cur_day,
                    prev_day=prev_day,
                    idx=i,
                )
        db.commit()
        print(f"  done：tasks={n_task} subtasks={n_sub} actions={n_act}")
        by_stage: dict[str, int] = {}
        for s in stage_of.values():
            by_stage[s] = by_stage.get(s, 0) + 1
        by_stage[REQ_STAGE_DEVELOPING] = n_task - sum(by_stage.values())
        print(f"  stages：{by_stage}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
