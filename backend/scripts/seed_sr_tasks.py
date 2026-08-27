"""
根据《TPT V2.3 产品包需求.xlsx》灌入测试数据。

- Project: TPT V2.3
- Domains: 平台 / 交付 / Agent / 定制
- Task: 每行 SR「系统需求名称」
- Subtask: 依据 SR「子类/模块」命名（条目多时拆为两期）
- Action: SR 描述的每个条目（按换行拆分）
- 给每条 Action 写一条最近日更（本周），进度 0~70% 随机，便于看板展示进度条/风险

用法（backend 目录）:
    python scripts/seed_sr_tasks.py
"""
from __future__ import annotations

import random
import re
import sys
import uuid
from datetime import date, datetime, time
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from collections import OrderedDict, defaultdict

import openpyxl
from sqlalchemy.orm import Session

from app.auth.models import User, UserRole
from app.auth.service import hash_password
from app.platform.database import SessionLocal
from app.test_manage.config import (
    PROJECT_STATUS_ACTIVE,
    REQ_STAGE_TESTING,
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
    TmWeekPeriod,
)
from app.test_manage.week import current_week_start, week_end, week_key

PROJECT_NAME = "TPT V2.3"
EXCEL_PATH = r"C:\Users\huangjing4\Documents\TPT V2.3 产品包需求.xlsx"
DEFAULT_PASSWORD = "123456"

DOMAIN_ORDER = ["平台", "交付", "Agent", "定制"]

DOMAIN_BY_EXCEL_CATEGORY = {
    "TPT平台": "平台",
    "智能控制Agents": "Agent",
    "回路优化Agents": "Agent",
    "报警管理Agents": "Agent",
    "设备健康监测Agents/设备诊断Agents": "定制",
    "utilities Agents": "定制",
    "计划调度优化Agents": "Agent",
    "公用工程优化Agents": "Agent",
    "换热网络评估优化Agents": "Agent",
    "智能仿真Agents": "Agent",
    "非功能性需求": "交付",
}

NONFUNC_TO_DOMAIN = {
    "性能需求": "定制",
    "安全性需求": "定制",
    "兼容性需求": "定制",
    "可服务性需求": "交付",
    "易用性需求": "交付",
}
INFRA_SUBCAT = "基础设施"

NAME_TO_USERNAME = OrderedDict(
    [
        ("黄婧", "hj"),
        ("袁小君", "xiaojun"),
        ("顾靖", "gujing"),
        ("刘义淑", "liuyishu"),
        ("丁乔", "dingqiao"),
        ("张莹", "zhangying"),
        ("朱婷卓", "zhutingzhuo"),
        ("叶学莉", "yexueli"),
        ("刘豪", "liuhao"),
        ("覃霜", "qinshuang"),
        ("姜静", "jiangjing"),
        ("孙厚凯", "sunhoukai"),
        ("刘佳", "liujia"),
        ("刘海晴", "liuhaiqing"),
        ("朱倩", "zhuqian"),
        ("余泽超", "yuzechao"),
    ]
)


def _new_uuid() -> str:
    return str(uuid.uuid4())


def _new_sid() -> str:
    return uuid.uuid4().hex[:12]


def _split_lines(text) -> list[str]:
    if not text:
        return []
    out: list[str] = []
    for raw in str(text).replace("\\", "/").split("\n"):
        ln = raw.strip()
        if not ln:
            continue
        ln = re.sub(r"^\s*[-•·]\s*", "", ln)
        out.append(ln)
    return out


def _dedup(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _domain_for(category: str, subcat: str) -> str:
    if category == "TPT平台" and subcat == INFRA_SUBCAT:
        return "交付"
    if category == "非功能性需求":
        return NONFUNC_TO_DOMAIN.get(subcat, "交付")
    return DOMAIN_BY_EXCEL_CATEGORY.get(category, "平台")


def _short_action_title(ln: str, subcat: str, idx: int) -> str:
    s = ln.strip()
    for prefix in ["对于每个", "对于", "支持通过", "支持", "提供", "实现", "完成", "新增", "能够", "可以"]:
        if s.startswith(prefix) and len(s) > len(prefix) + 4:
            s = s[len(prefix):]
            break
    for stop in ["，", "。", "；", ";", "、", ",", "."]:
        pos = s.find(stop)
        if 4 <= pos <= 16:
            return s[:pos]
    if len(s) <= 16:
        return s
    cut = s[:16]
    for stop in ["的", "了", "和", "与", "及", "等"]:
        p = cut.rfind(stop)
        if 5 <= p <= 15:
            return cut[:p]
    return cut


def _subtask_groups(subcat: str, lines: list[str]) -> list[tuple[str, list[str]]]:
    if len(lines) <= 6:
        return [(f"{subcat}子项", lines)]
    mid = (len(lines) + 1) // 2
    return [(f"{subcat}-一期", lines[:mid]), (f"{subcat}-二期", lines[mid:])]


def _ensure_users(db: Session) -> dict[str, User]:
    out: dict[str, User] = {}
    for cn, uname in NAME_TO_USERNAME.items():
        u = db.query(User).filter(User.username == uname).first()
        if not u:
            u = User(
                username=uname,
                real_name=cn,
                password_hash=hash_password(DEFAULT_PASSWORD),
                role=UserRole.Engineer,
            )
            db.add(u)
            db.flush()
        out[uname] = u
    admin = db.query(User).filter(User.username == "admin").first()
    if not admin:
        admin = User(
            username="admin",
            real_name="测试管理员",
            password_hash=hash_password(DEFAULT_PASSWORD),
            role=UserRole.Manager,
        )
        db.add(admin)
        db.flush()
    out["admin"] = admin
    db.commit()
    for u in out.values():
        db.refresh(u)
    return out


def _ensure_week(db: Session) -> tuple[str, datetime, datetime]:
    now = now_tm()
    key = week_key(now)
    ws = current_week_start(now)
    we = week_end(ws)
    w = db.query(TmWeekPeriod).filter(TmWeekPeriod.week_key == key).first()
    if not w:
        w = TmWeekPeriod(
            week_key=key,
            week_start=ws,
            week_end=we,
            created_by=None,
            updated_by=None,
        )
        db.add(w)
        db.commit()
    return key, ws, we


def _cleanup(db: Session, project: TmProject) -> None:
    task_ids = [t.id for t in db.query(TmTask).filter(TmTask.project_id == project.id).all()]
    if task_ids:
        db.query(TmTaskUpdateLog).filter(TmTaskUpdateLog.task_id.in_(task_ids)).delete(
            synchronize_session=False
        )
        db.query(TmTaskTester).filter(TmTaskTester.task_id.in_(task_ids)).delete(
            synchronize_session=False
        )
        act_ids = [a.id for a in db.query(TmAction).filter(TmAction.task_id.in_(task_ids)).all()]
        if act_ids:
            db.query(TmDailyUpdate).filter(TmDailyUpdate.action_id.in_(act_ids)).delete(
                synchronize_session=False
            )
            db.query(TmAction).filter(TmAction.id.in_(act_ids)).delete(synchronize_session=False)
        db.query(TmTask).filter(TmTask.id.in_(task_ids)).delete(synchronize_session=False)
    dom_ids = [d.id for d in db.query(TmDomain).filter(TmDomain.project_id == project.id).all()]
    if dom_ids:
        db.query(TmDomain).filter(TmDomain.id.in_(dom_ids)).delete(synchronize_session=False)
    db.query(TmPushSnapshot).filter(TmPushSnapshot.report_kind.like("tm:%")).delete(
        synchronize_session=False
    )
    db.query(TmPushRun).filter(TmPushRun.report_kind.like("tm:%")).delete(synchronize_session=False)
    db.commit()


def _load_excel() -> list[dict]:
    wb = openpyxl.load_workbook(EXCEL_PATH, data_only=True)
    ws = wb["产品包需求"]
    grouped: "OrderedDict[tuple[str,str,str],dict]" = OrderedDict()
    order: list[tuple[str, str, str]] = []
    for r in range(4, ws.max_row + 1):
        da = ws.cell(r, 7).value
        mo = ws.cell(r, 8).value
        nm = ws.cell(r, 9).value
        ds = ws.cell(r, 10).value
        sr = ws.cell(r, 5).value
        verifier = ws.cell(r, 16).value
        if not nm or not da:
            continue
        da = str(da).strip()
        mo = str(mo).strip() if mo else "其他"
        nm = str(nm).strip()
        key = (da, mo, nm)
        if key not in grouped:
            grouped[key] = {"srs": [], "lines": [], "verifier": str(verifier).strip() if verifier else ""}
            order.append(key)
        if sr:
            grouped[key]["srs"].append(str(sr))
        grouped[key]["lines"].extend(_split_lines(ds))
    out = []
    for da, mo, nm in order:
        info = grouped[key] if False else grouped[(da, mo, nm)]
        out.append(
            {
                "category": da,
                "subcat": mo,
                "title": nm,
                "sr_no": info["srs"][0] if info["srs"] else "",
                "lines": _dedup(info["lines"]),
                "verifier": info["verifier"],
            }
        )
    return out


def _wipe_all_tm_data(db: Session) -> None:
    print("Wiping all existing TM business data ...")
    db.query(TmDailyUpdate).delete(synchronize_session=False)
    db.query(TmActionCorrection).delete(synchronize_session=False)
    db.query(TmAction).delete(synchronize_session=False)
    db.query(TmTaskTester).delete(synchronize_session=False)
    db.query(TmTaskUpdateLog).delete(synchronize_session=False)
    db.query(TmTask).delete(synchronize_session=False)
    db.query(TmDomain).delete(synchronize_session=False)
    db.query(TmProject).delete(synchronize_session=False)
    db.query(TmPushSnapshot).delete(synchronize_session=False)
    db.query(TmPushRun).delete(synchronize_session=False)
    db.query(TmWeekPeriod).delete(synchronize_session=False)
    db.commit()


def seed(db: Session) -> None:
    if not Path(EXCEL_PATH).exists():
        print(f"ERROR: Excel not found at {EXCEL_PATH}")
        sys.exit(1)

    users = _ensure_users(db)
    unames = list(NAME_TO_USERNAME.values())
    admin = users["admin"]

    _wipe_all_tm_data(db)

    project = TmProject(
        name=PROJECT_NAME,
        description="TPT V2.3 产品包需求测试跟踪（按 SR 自动生成）",
        status=PROJECT_STATUS_ACTIVE,
        created_by=admin.id,
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    week_key_now, week_start_dt, _ = _ensure_week(db)

    dom_rows: dict[str, TmDomain] = {}
    for i, n in enumerate(DOMAIN_ORDER):
        d = TmDomain(name=n, project_id=project.id, sort_order=i)
        db.add(d)
        db.flush()
        dom_rows[n] = d
    db.commit()

    items = _load_excel()
    rng = random.Random(42)
    counts = defaultdict(int)
    n_actions = 0
    today = date.today()
    for idx, it in enumerate(items):
        domain_name = _domain_for(it["category"], it["subcat"])
        counts[domain_name] += 1
        dom = dom_rows[domain_name]
        lead_uname = unames[idx % len(unames)]
        tester_uname = unames[(idx + 3) % len(unames)]
        lead = users[lead_uname]
        tester = users[tester_uname] if tester_uname != lead_uname else None
        task_id = _new_uuid()
        task = TmTask(
            id=task_id,
            project_id=project.id,
            domain_id=dom.id,
            title=it["title"],
            requirement=f"{it['sr_no']} {it['title']}（{it['category']}/{it['subcat']}）",
            subtasks=[],
            lead_id=lead.id,
            status=TASK_STATUS_PUBLISHED,
            req_stage=REQ_STAGE_TESTING,
            created_by=admin.id,
            published_at=now_tm(),
        )
        db.add(task)
        db.add(TmTaskTester(task_id=task_id, user_id=lead.id))
        if tester is not None:
            db.add(TmTaskTester(task_id=task_id, user_id=tester.id))

        lines = it["lines"] or [f"{it['title']} - 功能验证"]
        groups = _subtask_groups(it["subcat"], lines)
        subtask_rows = []
        for st_name, st_lines in groups:
            sid = _new_sid()
            subtask_rows.append(
                {"sid": sid, "name": st_name, "content": f"{it['subcat']} 模块子需求", "deleted": False}
            )
            for j, ln in enumerate(st_lines):
                owner = lead if j % 2 == 0 else (tester or lead)
                progress = rng.choice([0, 10, 20, 30, 40, 50, 60, 70])
                risk = ""
                is_blocking = False
                if progress < 30 and rng.random() < 0.2:
                    risk = "环境待就绪"
                act_id = _new_uuid()
                short_title = _short_action_title(ln, it["subcat"], j)
                act = TmAction(
                    id=act_id,
                    task_id=task_id,
                    project_id=project.id,
                    domain_id=dom.id,
                    week_start=week_start_dt,
                    week_key=week_key_now,
                    title=short_title,
                    subtask_name=st_name,
                    initial_progress=0,
                    owner_id=owner.id,
                    test_content=ln,
                    environment="test 环境",
                    status=STATUS_PUBLISHED,
                    source_action_id=None,
                    created_by=owner.id,
                    published_at=now_tm(),
                )
                db.add(act)
                if progress > 0 or risk:
                    db.add(
                        TmDailyUpdate(
                            action_id=act_id,
                            user_id=owner.id,
                            report_date=today,
                            progress_percent=progress,
                            risk_blocker=risk,
                            is_blocking=is_blocking,
                            progress_note=f"推进中（{progress}%）" if progress else "",
                        )
                    )
                n_actions += 1
        task.subtasks = subtask_rows
        db.flush()

    db.commit()
    print(f"Project: {PROJECT_NAME}")
    for dn in DOMAIN_ORDER:
        print(f"  Domain {dn}: {counts[dn]} tasks")
    print(f"Total tasks: {len(items)}, actions: {n_actions}")


def main() -> None:
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
