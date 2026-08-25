"""业务周结束 → 周报发送时刻 / 周截止前编辑锁规则。"""
from datetime import timedelta

from app.platform.database import SessionLocal
from app.test_manage.config import TM_TZ, now_tm
from app.test_manage.period import (
    compute_weekly_push_at,
    get_or_create_active_period,
    is_week_edit_locked,
)


def _dt(y: int, m: int, d: int, hh: int, mm: int = 0):
    from datetime import datetime

    return datetime(y, m, d, hh, mm, tzinfo=TM_TZ)


def test_weekly_push_always_fifteen_after_afternoon_end():
    """周结束 15:00 → 15:15。"""
    assert compute_weekly_push_at(_dt(2026, 7, 29, 15, 0)) == _dt(2026, 7, 29, 15, 15)


def test_weekly_push_always_fifteen_after_seventeen():
    """周结束 17:00 → 17:15。"""
    assert compute_weekly_push_at(_dt(2026, 7, 29, 17, 0)) == _dt(2026, 7, 29, 17, 15)


def test_weekly_push_always_fifteen_after_default_end():
    """周结束 18:00 → 18:15。"""
    assert compute_weekly_push_at(_dt(2026, 7, 29, 18, 0)) == _dt(2026, 7, 29, 18, 15)


def test_week_edit_lock_window(client, auth_headers):
    """周截止前 5 分钟编辑锁：锁定窗内更新 Task / 创建 Action 均 400。"""
    db = SessionLocal()
    per = get_or_create_active_period(db)
    original_end = per.week_end
    try:
        # 正常时刻（离周结束远）：未锁
        assert is_week_edit_locked(db) is False

        # 把活动周结束拉近到 2 分钟后 → 落入「week_end 前 5 分钟」锁定窗
        per.week_end = now_tm() + timedelta(minutes=2)
        db.commit()
        assert is_week_edit_locked(db) is True

        # 锁定窗内：更新 Task → 400
        r = client.patch(
            f"/api/test-manage/tasks/{_lock_seed_task(client, auth_headers)}",
            json={"requirement": "锁定窗内改需求"},
            headers=auth_headers,
        )
        assert r.status_code == 400, r.text
        assert "锁定" in r.json()["detail"]

        # 锁定窗内：创建 Action → 400
        r = client.post(
            "/api/test-manage/actions",
            json={
                "task_id": _lock_seed_task(client, auth_headers),
                "title": "锁定窗内建 Action",
                "test_content": "内容",
                "environment": "qa",
                "publish": True,
            },
            headers=auth_headers,
        )
        assert r.status_code == 400, r.text
        assert "锁定" in r.json()["detail"]
    finally:
        # 还原周窗口，避免污染共享测试库的后续用例
        db.rollback()
        from app.test_manage.models import TmWeekPeriod

        per2 = db.query(TmWeekPeriod).filter(TmWeekPeriod.id == per.id).first()
        if per2 is not None:
            per2.week_end = original_end
            db.commit()
        db.close()


_LOCK_TASK_CACHE: dict[str, str] = {}


def _lock_seed_task(client, headers) -> str:
    """惰性创建一个 testing 状态 Task（同一测试内复用）。"""
    if "task_id" in _LOCK_TASK_CACHE:
        return _LOCK_TASK_CACHE["task_id"]
    r = client.post("/api/test-manage/projects", json={"name": "P-lock"}, headers=headers)
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    r = client.post(
        f"/api/test-manage/projects/{pid}/domains", json={"name": "D"}, headers=headers
    )
    assert r.status_code == 201, r.text
    did = r.json()["id"]
    r = client.get("/api/test-manage/users", headers=headers)
    uid = next(u["id"] for u in r.json() if u["username"] == "admin")
    r = client.post(
        "/api/test-manage/tasks",
        json={
            "project_id": pid,
            "domain_id": did,
            "title": "Lock-Task",
            "requirement": "锁定窗测试",
            "lead_id": uid,
            "tester_ids": [],
            "publish": True,
            "req_stage": "testing",
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    _LOCK_TASK_CACHE["task_id"] = r.json()["id"]
    return _LOCK_TASK_CACHE["task_id"]
