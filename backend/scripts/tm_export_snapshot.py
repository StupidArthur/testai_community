"""
从开发库导出 TPT v2.1 项目真实业务数据快照（含用户映射），供 64 生产机导入。

用法（在 backend 目录）：
    python scripts/tm_export_snapshot.py
    # 可选参数：--project "TPT v2.1"（默认）  --out tm_snapshot.json

产出：backend/scripts/tm_snapshot.json
- 用户只导出 username/real_name/role（密码不导，导入端统一 123456）
- id 全部保留原 UUID，导入端仅重映射 user_id（两库用户表自增 id 不同）
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

DEFAULT_PROJECT = "TPT v2.1"
DEFAULT_OUT = _BACKEND / "scripts" / "tm_snapshot.json"


def export_snapshot(db_path: Path, project_name: str) -> dict:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    try:
        proj = cur.execute(
            "SELECT * FROM tm_projects WHERE name=? ORDER BY created_at DESC LIMIT 1",
            (project_name,),
        ).fetchone()
        if not proj:
            raise RuntimeError(f"未找到项目 {project_name}")
        pid = proj["id"]

        domains = [
            dict(r)
            for r in cur.execute(
                "SELECT * FROM tm_domains WHERE project_id=? ORDER BY sort_order, created_at",
                (pid,),
            )
        ]
        tasks = [dict(r) for r in cur.execute("SELECT * FROM tm_tasks WHERE project_id=? ORDER BY created_at", (pid,))]
        tids = [t["id"] for t in tasks]

        testers: list[dict] = []
        logs: list[dict] = []
        week_progress: list[dict] = []
        if tids:
            ph = ",".join("?" * len(tids))
            testers = [dict(r) for r in cur.execute(f"SELECT * FROM tm_task_testers WHERE task_id IN ({ph}) ORDER BY created_at", tids)]
            logs = [dict(r) for r in cur.execute(f"SELECT * FROM tm_task_update_logs WHERE task_id IN ({ph}) ORDER BY created_at", tids)]
            week_progress = [dict(r) for r in cur.execute(f"SELECT * FROM tm_task_week_progress WHERE task_id IN ({ph}) ORDER BY created_at", tids)]

        actions = [dict(r) for r in cur.execute("SELECT * FROM tm_actions WHERE project_id=? ORDER BY created_at", (pid,))]
        aids = [a["id"] for a in actions]
        corrections: list[dict] = []
        dailies: list[dict] = []
        if aids:
            ph = ",".join("?" * len(aids))
            corrections = [dict(r) for r in cur.execute(f"SELECT * FROM tm_action_corrections WHERE action_id IN ({ph}) ORDER BY created_at", aids)]
            dailies = [dict(r) for r in cur.execute(f"SELECT * FROM tm_daily_updates WHERE action_id IN ({ph}) ORDER BY report_date", aids)]

        # 涉及的用户（lead/owner/created_by/tester/log 任意角色）
        user_ids: set[int] = set()
        for t in tasks:
            user_ids.add(t["lead_id"])
            user_ids.add(t["created_by"])
        for a in actions:
            user_ids.add(a["owner_id"])
            user_ids.add(a["created_by"])
        for x in testers + logs + corrections + dailies:
            user_ids.add(x["user_id"])
        for wp in week_progress:
            user_ids.add(wp["updated_by"])
        users = [
            dict(r)
            for r in cur.execute(
                f"SELECT id, username, real_name, role, created_at FROM users WHERE id IN ({','.join('?' * len(user_ids))}) ORDER BY id",
                sorted(user_ids),
            )
        ]

        snapshot = {
            "meta": {
                "source": str(db_path),
                "project_name": proj["name"],
                "exported_at": None,  # 导入端不关心，留空
            },
            "project": {
                "id": proj["id"],
                "name": proj["name"],
                "description": proj["description"],
                "status": proj["status"],
            },
            "users": [
                {
                    "id": u["id"],
                    "username": u["username"],
                    "real_name": u["real_name"],
                    "role": u["role"],
                }
                for u in users
            ],
            "domains": domains,
            "tasks": tasks,
            "task_testers": testers,
            "task_update_logs": logs,
            "task_week_progress": week_progress,
            "actions": actions,
            "action_corrections": corrections,
            "daily_updates": dailies,
        }
        return snapshot
    finally:
        conn.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(_BACKEND / "database_dev.sqlite"))
    ap.add_argument("--project", default=DEFAULT_PROJECT)
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        raise SystemExit(f"库不存在: {db_path}")

    snap = export_snapshot(db_path, args.project)
    out = Path(args.out)
    out.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"== export tm snapshot ==")
    print(f"  db={db_path}")
    print(
        f"  project={snap['project']['name']} domains={len(snap['domains'])} "
        f"tasks={len(snap['tasks'])} actions={len(snap['actions'])} "
        f"daily_updates={len(snap['daily_updates'])} corrections={len(snap['action_corrections'])} "
        f"week_progress={len(snap['task_week_progress'])} users={len(snap['users'])}"
    )
    week_keys = sorted({a["week_key"] for a in snap["actions"]})
    print(f"  action week_keys={week_keys}")
    report_days = sorted({d["report_date"] for d in snap["daily_updates"]})
    print(f"  daily report_dates={report_days}")
    print(f"  OUT={out}")


if __name__ == "__main__":
    main()
