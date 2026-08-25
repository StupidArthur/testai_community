"""
将开发机导出的 TPT 真实业务快照导入当前库（在 64 生产机 backend 目录执行）。

用法：
    python scripts/tm_import_snapshot.py
    python scripts/tm_import_snapshot.py --db sqlite:///./database.sqlite
    python scripts/tm_import_snapshot.py --keep-push   # 不清推送快照/幂等记录

行为：
- 用户按 username 匹配；缺失则自动创建（密码统一 123456）
- 删除当前库同名项目（默认 TPT v2.1）及其全部下级数据后重建（id 沿用源库 UUID）
- Action 周锚定：源最新周 → 当前活动周（get_daily_context_period），更早的周依次 -7 天
- 日更与时间戳整体平移：源最新日更日 → 今天（保持真实内容与相对间隔）
- 默认清空 tm_push_snapshots / tm_push_runs，让下次日报做干净的全量对比
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

parser = argparse.ArgumentParser()
parser.add_argument("--snapshot", default=str(_BACKEND / "scripts" / "tm_snapshot.json"))
parser.add_argument("--db", default=None, help="覆盖 DATABASE_URL，如 sqlite:///./database.sqlite")
parser.add_argument("--keep-push", action="store_true", help="保留推送快照与幂等记录")
args = parser.parse_args()

try:
    from dotenv import load_dotenv

    load_dotenv(_BACKEND.parent / ".env")
    load_dotenv(_BACKEND / ".env")
except Exception:
    pass
if args.db:
    os.environ["DATABASE_URL"] = args.db

from sqlalchemy.orm import Session  # noqa: E402

from app.auth.models import User, UserRole  # noqa: E402
from app.auth.service import hash_password  # noqa: E402
from app.platform.database import SessionLocal  # noqa: E402
from app.test_manage.config import now_tm  # noqa: E402
from app.test_manage.models import (  # noqa: E402
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
)
from app.test_manage.period import get_daily_context_period  # noqa: E402
from app.test_manage.week import week_end, week_key  # noqa: E402

DEFAULT_PASSWORD = "123456"


def _dt(v) -> datetime | None:
    if v in (None, ""):
        return None
    if isinstance(v, datetime):
        return v
    return datetime.fromisoformat(str(v).replace(" ", "T").rstrip("Z"))


def _d(v) -> date | None:
    if v in (None, ""):
        return None
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])


def import_snapshot(db: Session, snap: dict, *, clear_push: bool) -> None:
    proj_info = snap["project"]
    project_name = proj_info["name"]

    admin = (
        db.query(User)
        .filter(User.role.in_([UserRole.Admin, UserRole.Manager]))
        .order_by(User.id.asc())
        .first()
    )
    if not admin:
        raise RuntimeError("当前库没有 Admin/Manager 用户，请先确认连对了库")

    print("== import tm snapshot ==")
    print(f"  DATABASE_URL={os.getenv('DATABASE_URL')}")

    # 1) 用户按 username 匹配 / 创建
    uid: dict[str, int] = {}
    created_users = 0
    for u in snap["users"]:
        username = u["username"]
        row = db.query(User).filter(User.username == username).first()
        if not row:
            row = User(
                username=username,
                password_hash=hash_password(DEFAULT_PASSWORD),
                role=UserRole(u["role"]),
                real_name=u.get("real_name"),
            )
            db.add(row)
            db.flush()
            created_users += 1
        elif not (row.real_name or "").strip() and u.get("real_name"):
            # 已存在用户缺真实姓名时补上（日报展示用真实姓名）
            row.real_name = u["real_name"]
        uid[username] = row.id
    print(f"  users: {len(snap['users'])} (created={created_users})")

    # 源库数字 user_id → username 映射（导出 json 中的 lead_id/owner_id 等仍是源库数字 id）
    src_id_to_username: dict[int, str] = {u["id"]: u["username"] for u in snap["users"]}

    # 2) 删除当前库同名项目 / 同 id 项目的全部下级数据
    pids = {
        p.id
        for p in db.query(TmProject).filter(TmProject.name == project_name).all()
    }
    src_pid = proj_info["id"]
    if db.query(TmProject).filter(TmProject.id == src_pid).first():
        pids.add(src_pid)
    if pids:
        pid_list = list(pids)
        tids = [t.id for t in db.query(TmTask.id).filter(TmTask.project_id.in_(pid_list)).all()]
        if tids:
            aids = [
                a.id
                for a in db.query(TmAction.id).filter(TmAction.task_id.in_(tids)).all()
            ]
            if aids:
                db.query(TmDailyUpdate).filter(TmDailyUpdate.action_id.in_(aids)).delete(
                    synchronize_session=False
                )
                db.query(TmActionCorrection).filter(
                    TmActionCorrection.action_id.in_(aids)
                ).delete(synchronize_session=False)
            db.query(TmAction).filter(TmAction.task_id.in_(tids)).delete(
                synchronize_session=False
            )
            db.query(TmTaskWeekProgress).filter(
                TmTaskWeekProgress.task_id.in_(tids)
            ).delete(synchronize_session=False)
            db.query(TmTaskUpdateLog).filter(TmTaskUpdateLog.task_id.in_(tids)).delete(
                synchronize_session=False
            )
            db.query(TmTaskTester).filter(TmTaskTester.task_id.in_(tids)).delete(
                synchronize_session=False
            )
        db.query(TmTask).filter(TmTask.project_id.in_(pid_list)).delete(
            synchronize_session=False
        )
        db.query(TmDomain).filter(TmDomain.project_id.in_(pid_list)).delete(
            synchronize_session=False
        )
        db.query(TmProject).filter(TmProject.id.in_(pid_list)).delete(
            synchronize_session=False
        )
        db.flush()
        print(f"  removed old project rows: projects={len(pid_list)} tasks={len(tids)}")

    # 3) 周锚定：源最新周 → 当前活动周；更早的周依次 -7 天
    ctx = get_daily_context_period(db)
    src_weeks = sorted({a["week_key"] for a in snap["actions"]})
    week_map: dict[str, tuple[datetime, str, datetime]] = {}
    for i, wk in enumerate(reversed(src_weeks)):
        ws = ctx.week_start - timedelta(days=7 * i)
        week_map[wk] = (ws, week_key(ws), week_end(ws))
    print(f"  week anchor: {src_weeks} -> {[week_map[w][1] for w in src_weeks]}")

    # 4) 日更平移：源最新日更日 → 今天
    today = now_tm().date()
    if snap["daily_updates"]:
        max_rd = max(_d(x["report_date"]) for x in snap["daily_updates"])
        offset = timedelta(days=(today - max_rd).days)
    else:
        offset = timedelta(days=0)
    print(f"  daily shift: latest {max_rd if snap['daily_updates'] else '-'} -> {today} (+{offset.days}d)")

    # 5) 重建
    proj = TmProject(
        id=src_pid,
        name=proj_info["name"],
        description=proj_info.get("description"),
        status=proj_info.get("status") or "active",
        created_by=admin.id,
    )
    db.add(proj)
    db.flush()

    domain_map = {d["id"]: d for d in snap["domains"]}
    for d in snap["domains"]:
        db.add(
            TmDomain(
                id=d["id"],
                project_id=src_pid,
                name=d["name"],
                sort_order=d.get("sort_order") or 0,
            )
        )
    db.flush()

    task_rows = {t["id"]: t for t in snap["tasks"]}
    for t in snap["tasks"]:
        db.add(
            TmTask(
                id=t["id"],
                project_id=src_pid,
                domain_id=t["domain_id"],
                title=t["title"],
                requirement=t.get("requirement") or "",
                lead_id=uid[src_id_to_username[t["lead_id"]]],
                status=t["status"],
                req_stage=t.get("req_stage") or "testing",
                expected_handover_at=_shift(_d(t.get("expected_handover_at")), offset),
                actual_handover_at=_shift(_d(t.get("actual_handover_at")), offset),
                test_started_at=_shift(_d(t.get("test_started_at")), offset),
                expected_test_end_at=_shift(_d(t.get("expected_test_end_at")), offset),
                test_ended_at=_shift(_d(t.get("test_ended_at")), offset),
                created_by=uid[src_id_to_username[t["created_by"]]],
                published_at=_shift(_dt(t.get("published_at")), offset),
            )
        )
    db.flush()

    for x in snap["task_testers"]:
        db.add(
            TmTaskTester(
                id=x["id"],
                task_id=x["task_id"],
                user_id=uid[src_id_to_username[x["user_id"]]],
            )
        )
    for x in snap["task_update_logs"]:
        db.add(
            TmTaskUpdateLog(
                id=x["id"],
                task_id=x["task_id"],
                user_id=uid[src_id_to_username[x["user_id"]]],
                summary=x.get("summary") or "",
                detail=x.get("detail") or "",
            )
        )
    db.flush()

    n_published = 0
    for a in snap["actions"]:
        ws, wk, we = week_map[a["week_key"]]
        if a["status"] == "published":
            n_published += 1
        db.add(
            TmAction(
                id=a["id"],
                task_id=a["task_id"],
                project_id=src_pid,
                domain_id=a["domain_id"],
                week_start=ws,
                week_key=wk,
                title=a["title"],
                owner_id=uid[src_id_to_username[a["owner_id"]]],
                test_content=a.get("test_content") or "",
                environment=a.get("environment") or "",
                status=a["status"],
                source_action_id=a.get("source_action_id"),
                created_by=uid[src_id_to_username[a["created_by"]]],
                published_at=_shift(_dt(a.get("published_at")), offset),
                due_at=we,
            )
        )
    db.flush()

    for x in snap["action_corrections"]:
        db.add(
            TmActionCorrection(
                id=x["id"],
                action_id=x["action_id"],
                user_id=uid[src_id_to_username[x["user_id"]]],
                note=x.get("note") or "",
            )
        )
    for x in snap["daily_updates"]:
        db.add(
            TmDailyUpdate(
                id=x["id"],
                action_id=x["action_id"],
                user_id=uid[src_id_to_username[x["user_id"]]],
                report_date=_shift(_d(x["report_date"]), offset),
                progress_percent=x.get("progress_percent") or 0,
                risk_blocker=x.get("risk_blocker") or "",
                is_blocking=bool(x.get("is_blocking")),
                progress_note=x.get("progress_note") or "",
            )
        )
    for x in snap["task_week_progress"]:
        db.add(
            TmTaskWeekProgress(
                id=x["id"],
                task_id=x["task_id"],
                week_key=week_map[x["week_key"]][1],
                progress_percent=x.get("progress_percent") or 0,
                note=x.get("note") or "",
                updated_by=uid[src_id_to_username[x["updated_by"]]],
            )
        )
    db.flush()

    # 6) 清推送状态（可选）：让下次日报做干净的全量对比
    if clear_push:
        n1 = db.query(TmPushSnapshot).delete(synchronize_session=False)
        n2 = db.query(TmPushRun).delete(synchronize_session=False)
        print(f"  cleared push snapshots={n1} runs={n2}")

    db.commit()
    print(
        f"  DONE project={project_name} domains={len(snap['domains'])} "
        f"tasks={len(snap['tasks'])} actions={len(snap['actions'])} "
        f"(published={n_published}) daily_updates={len(snap['daily_updates'])} "
        f"today={today} active_week={ctx.week_key}"
    )


def _shift(v, offset: timedelta):
    if v is None:
        return None
    return v + offset


def main() -> None:
    snap_path = Path(args.snapshot)
    if not snap_path.exists():
        raise SystemExit(f"快照不存在: {snap_path}")
    snap = json.loads(snap_path.read_text(encoding="utf-8"))

    db = SessionLocal()
    try:
        import_snapshot(db, snap, clear_push=not args.keep_push)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
