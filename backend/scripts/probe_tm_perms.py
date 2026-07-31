"""现场探针：不同账号登录、推送、建 Action。在 backend 下 python scripts/probe_tm_perms.py"""
from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from fastapi.testclient import TestClient
from sqlalchemy.orm import joinedload

from app.auth.models import User
from app.platform.database import SessionLocal
from app.platform.factory import app
from app.test_manage.models import TmAction
from app.test_manage.push_report import collect_progress_summary
from app.test_manage.service import _latest_progress, get_board, list_mine_actions
from app.test_manage.week import current_week_start, week_key

c = TestClient(app)


def login(u: str, p: str):
    r = c.post("/api/auth/login", json={"username": u, "password": p})
    detail = r.json().get("detail") if r.status_code != 200 else r.json()["user"]["role"]
    print(f"login {u}: {r.status_code} -> {detail}")
    if r.status_code != 200:
        return None
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def main() -> None:
    print("=== login matrix ===")
    ha = login("admin", "admin")
    hm = login("manager", "123456")
    hh = login("hj", "123456")
    login("无", "123456")
    ht = login("tongshuang", "123456")

    print("=== push perms ===")
    for name, h in [("hj", hh), ("manager", hm), ("admin", ha)]:
        if not h:
            continue
        r = c.post("/api/test-manage/push/daily", json={"dry_run": True}, headers=h)
        print(f"  {name} dry_run daily: {r.status_code} {r.json() if r.status_code < 500 else r.text[:80]}")

    if ha:
        r = c.post(
            "/api/test-manage/push/daily",
            json={"dry_run": False, "force": False},
            headers=ha,
        )
        print(f"  admin real push: {r.status_code} {r.json() if r.status_code < 500 else r.text[:120]}")

    print("=== create action on published task ===")
    if ha:
        board = c.get("/api/test-manage/board", headers=ha).json()
        t = board["tasks"][0]["task"]
        r = c.post(
            "/api/test-manage/actions",
            json={
                "task_id": t["id"],
                "title": "probe-extra-delete-me",
                "owner_id": t["lead_id"],
                "publish": False,
            },
            headers=ha,
        )
        print(f"  create draft: {r.status_code}")
        if r.status_code == 201:
            aid = r.json()["id"]
            # engineer cannot publish others?
            if hh:
                r2 = c.patch(
                    f"/api/test-manage/actions/{aid}",
                    json={"status": "published"},
                    headers=hh,
                )
                print(f"  hj publish admin-created action: {r2.status_code} {r2.json().get('detail')}")
            c.patch(
                f"/api/test-manage/actions/{aid}",
                json={"status": "cancelled"},
                headers=ha,
            )
            print("  cleaned: cancelled probe action")

    print("=== mine / board counts ===")
    db = SessionLocal()
    try:
        wk = week_key(current_week_start())
        for uname in ("hj", "tongshuang", "xiaojun", "admin"):
            u = db.query(User).filter(User.username == uname).first()
            if not u:
                continue
            mine = list_mine_actions(db, u)
            board = get_board(db, u)
            print(
                f"  {uname}: mine={len(mine)} board_tasks={len(board.tasks)} "
                f"board_actions={board.summary.action_count}"
            )
        s = collect_progress_summary(db)
        admin = db.query(User).filter(User.username == "admin").first()
        b = get_board(db, admin)
        print(
            f"  weekly.published={s.published_count} board.published={b.summary.published_count} "
            f"weekly.risk={s.risk_action_count} board.risk={b.summary.risk_action_count}"
        )
        acts = (
            db.query(TmAction)
            .options(joinedload(TmAction.daily_updates))
            .filter(TmAction.week_key == wk)
            .all()
        )
        open_n = sum(1 for a in acts if (_latest_progress(a)[1] or "").strip())
        print(f"  current week open-risk actions (via _latest_progress)={open_n}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
