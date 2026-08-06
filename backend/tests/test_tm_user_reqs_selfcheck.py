"""
用户需求自测（三点）：
1. Task 未手填进度 → 推荐 Action 平均
2. Manager 可改周结束；创建 Action 挂当前活动周 due_at
3. Action 延续历史 weeks_count
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from app.platform.database import SessionLocal
from app.test_manage.config import now_tm
from app.test_manage.models import TmAction
from app.test_manage.period import compute_weekly_push_at
from app.test_manage.week import week_key as week_key_fn


@pytest.fixture()
def mgr_headers(client):
    r = client.post("/api/auth/login", json={"username": "manager", "password": "123456"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _users(client, headers):
    r = client.get("/api/test-manage/users", headers=headers)
    assert r.status_code == 200
    return {u["username"]: u for u in r.json()}


def _seed(client, mgr_headers, name: str):
    r = client.post(
        "/api/test-manage/projects",
        json={"name": name},
        headers=mgr_headers,
    )
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    r = client.post(
        f"/api/test-manage/projects/{pid}/domains",
        json={"name": "Agent"},
        headers=mgr_headers,
    )
    assert r.status_code == 201, r.text
    return pid, r.json()["id"]


def _seed_task(client, mgr_headers, pid, did, lead_id, title="Req-Task"):
    r = client.post(
        "/api/test-manage/tasks",
        json={
            "project_id": pid,
            "domain_id": did,
            "title": title,
            "requirement": "需求",
            "lead_id": lead_id,
            "tester_ids": [],
            "publish": True,
        },
        headers=mgr_headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_1_task_unfilled_progress_recommends_action_avg(
    client, mgr_headers, eng_headers
):
    """需求1：未手填 Task 进度时，展示/推荐为本周 Action 平均。"""
    users = _users(client, mgr_headers)
    pid, did = _seed(client, mgr_headers, "P-rec")
    task = _seed_task(
        client, mgr_headers, pid, did, users["eng_test"]["id"], title="Rec-Task"
    )
    r = client.post(
        "/api/test-manage/actions",
        json={
            "task_id": task["id"],
            "title": "A1",
            "test_content": "测",
            "environment": "qa",
            "publish": True,
        },
        headers=eng_headers,
    )
    assert r.status_code == 201, r.text
    aid = r.json()["id"]
    r = client.put(
        f"/api/test-manage/actions/{aid}/daily-updates",
        json={"progress_percent": 60, "progress_note": "本日进展说明足够长"},
        headers=eng_headers,
    )
    assert r.status_code == 200, r.text

    r = client.get(
        f"/api/test-manage/tasks/{task['id']}/week-progress",
        headers=mgr_headers,
    )
    assert r.status_code == 200, r.text
    wp = r.json()
    assert wp["progress_is_manual"] is False
    assert wp["recommended_progress"] == 60
    assert wp["progress_percent"] == 60

    r = client.get("/api/test-manage/board", headers=mgr_headers)
    assert r.status_code == 200
    hit = next(t for t in r.json()["tasks"] if t["task"]["id"] == task["id"])
    assert hit["progress_is_manual"] is False
    assert hit["recommended_progress"] == 60
    assert hit["week_progress_avg"] == 60


def test_2_manager_sets_week_end_and_action_uses_it(
    client, mgr_headers, eng_headers
):
    """需求2：Manager 可改周结束；创建 Action 的 due_at 跟活动周；Engineer 无权改。"""
    users = _users(client, mgr_headers)
    pid, did = _seed(client, mgr_headers, "P-week")
    task = _seed_task(
        client, mgr_headers, pid, did, users["eng_test"]["id"], title="Week-Task"
    )

    r = client.get("/api/test-manage/week", headers=mgr_headers)
    assert r.status_code == 200, r.text
    week = r.json()
    assert week["can_set_week_end"] is True

    new_end = (now_tm() + timedelta(days=2)).replace(second=0, microsecond=0)
    r = client.put(
        "/api/test-manage/week/end",
        json={"week_end": new_end.isoformat()},
        headers=mgr_headers,
    )
    assert r.status_code == 200, r.text
    updated = r.json()
    assert updated["weekly_push_at"] is not None
    # 周报 = 结束 + 15 分钟
    push = compute_weekly_push_at(new_end)
    assert updated["weekly_push_at"].startswith(push.strftime("%Y-%m-%dT%H:%M"))

    r = client.put(
        "/api/test-manage/week/end",
        json={"week_end": (now_tm() + timedelta(days=3)).isoformat()},
        headers=eng_headers,
    )
    assert r.status_code == 403

    r = client.post(
        "/api/test-manage/actions",
        json={
            "task_id": task["id"],
            "title": "挂当前周",
            "test_content": "内容",
            "environment": "qa",
            "publish": False,
        },
        headers=mgr_headers,
    )
    assert r.status_code == 201, r.text
    act = r.json()
    assert act["due_at"] is not None
    # due_at 应对齐刚设置的 week_end（允许 ISO 时区写法差异）
    assert act["due_at"][:16] == updated["week_end"][:16]
    assert act["week_key"] == updated["week_key"] or act["week_key"] == week_key_fn(
        __import__("datetime").datetime.fromisoformat(
            updated["week_start"].replace("Z", "+00:00")
        )
    )


def test_3_action_lineage_weeks_count(client, mgr_headers, eng_headers):
    """需求3：克隆延续后 lineage.weeks_count >= 2，并带 source 链。"""
    users = _users(client, mgr_headers)
    pid, did = _seed(client, mgr_headers, "P-lin")
    task = _seed_task(
        client, mgr_headers, pid, did, users["eng_test"]["id"], title="Lin-Task"
    )
    r = client.post(
        "/api/test-manage/actions",
        json={
            "task_id": task["id"],
            "title": "W1",
            "test_content": "周1内容",
            "environment": "qa",
            "publish": True,
        },
        headers=eng_headers,
    )
    assert r.status_code == 201, r.text
    src_id = r.json()["id"]
    client.put(
        f"/api/test-manage/actions/{src_id}/daily-updates",
        json={
            "progress_percent": 40,
            "progress_note": "第一周进展说明",
            "risk_blocker": "环境不稳",
        },
        headers=eng_headers,
    )

    # 把源 Action 挪到「上周」才能出现在 clone-candidates / 模拟跨周
    db = SessionLocal()
    try:
        row = db.query(TmAction).filter(TmAction.id == src_id).one()
        prev_start = row.week_start - timedelta(days=7)
        row.week_start = prev_start
        row.week_key = week_key_fn(prev_start)
        row.due_at = prev_start + timedelta(days=7)
        db.commit()
    finally:
        db.close()

    r = client.post(
        f"/api/test-manage/actions/{src_id}/clone",
        json={"publish": False},
        headers=eng_headers,
    )
    assert r.status_code == 201, r.text
    cloned = r.json()
    assert cloned["source_action_id"] == src_id

    r = client.get(
        f"/api/test-manage/actions/{cloned['id']}/lineage",
        headers=mgr_headers,
    )
    assert r.status_code == 200, r.text
    lin = r.json()
    assert lin["weeks_count"] == 2
    assert len(lin["segments"]) == 2
    assert any(s["action_id"] == src_id for s in lin["segments"])
    assert any(s["action_id"] == cloned["id"] and s["is_current"] for s in lin["segments"])
    risks = [rsk for s in lin["segments"] for rsk in (s.get("risks") or [])]
    assert "环境不稳" in risks
