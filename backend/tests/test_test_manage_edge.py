"""
test_manage 异常 / 边界 / 校验场景。
依赖 tests/test_test_manage.py 中的 helper 模式（本文件自包含）。
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.test_manage.config import TM_TZ
from app.test_manage.week import current_week_start


@pytest.fixture()
def mgr_headers(client):
    r = client.post("/api/auth/login", json={"username": "manager", "password": "123456"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def eng2_headers(client, auth_headers):
    r = client.post(
        "/api/auth/add-user",
        json={"username": "eng_edge", "password": "eng123456", "role": "Engineer"},
        headers=auth_headers,
    )
    if r.status_code != 200:
        r = client.post(
            "/api/auth/login",
            json={"username": "eng_edge", "password": "eng123456"},
        )
        assert r.status_code == 200
        token = r.json()["access_token"]
    else:
        token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _users(client, headers):
    r = client.get("/api/test-manage/users", headers=headers)
    assert r.status_code == 200
    return {u["username"]: u for u in r.json()}


def _seed(client, mgr_headers, name: str):
    r = client.post("/api/test-manage/projects", json={"name": name}, headers=mgr_headers)
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    r = client.post(
        f"/api/test-manage/projects/{pid}/domains",
        json={"name": "Dom"},
        headers=mgr_headers,
    )
    assert r.status_code == 201
    return pid, r.json()["id"]


def _task(client, mgr_headers, pid, did, lead_id, **kw):
    body = {
        "project_id": pid,
        "domain_id": did,
        "title": kw.get("title", "T"),
        "requirement": kw.get("requirement", "req"),
        "lead_id": lead_id,
        "tester_ids": kw.get("tester_ids", []),
        "publish": kw.get("publish", True),
    }
    r = client.post("/api/test-manage/tasks", json=body, headers=mgr_headers)
    assert r.status_code == 201, r.text
    return r.json()


# ── 404 / 不存在 ─────────────────────────────────────────────


def test_get_missing_task_404(client, mgr_headers):
    r = client.get("/api/test-manage/tasks/not-exist-id", headers=mgr_headers)
    assert r.status_code == 404


def test_get_missing_action_404(client, mgr_headers):
    r = client.get("/api/test-manage/actions/not-exist-id", headers=mgr_headers)
    assert r.status_code == 404


def test_patch_missing_project_404(client, mgr_headers):
    r = client.patch(
        "/api/test-manage/projects/nope",
        json={"name": "x"},
        headers=mgr_headers,
    )
    assert r.status_code == 404


def test_domain_on_missing_project_404(client, mgr_headers):
    r = client.post(
        "/api/test-manage/projects/nope/domains",
        json={"name": "D"},
        headers=mgr_headers,
    )
    assert r.status_code == 404


def test_clone_missing_action_404(client, mgr_headers, eng_headers):
    r = client.post(
        "/api/test-manage/actions/missing/clone",
        json={},
        headers=eng_headers,
    )
    assert r.status_code == 404


# ── 校验边界 ─────────────────────────────────────────────────


def test_empty_project_name_422(client, mgr_headers):
    r = client.post(
        "/api/test-manage/projects",
        json={"name": ""},
        headers=mgr_headers,
    )
    assert r.status_code == 422


def test_empty_task_title_422(client, mgr_headers):
    users = _users(client, mgr_headers)
    pid, did = _seed(client, mgr_headers, "P-empty-title")
    r = client.post(
        "/api/test-manage/tasks",
        json={
            "project_id": pid,
            "domain_id": did,
            "title": "",
            "lead_id": users["eng_test"]["id"],
        },
        headers=mgr_headers,
    )
    assert r.status_code == 422


def test_empty_action_title_422(client, mgr_headers, eng_headers):
    users = _users(client, mgr_headers)
    pid, did = _seed(client, mgr_headers, "P-act-empty")
    task = _task(client, mgr_headers, pid, did, users["eng_test"]["id"])
    r = client.post(
        "/api/test-manage/actions",
        json={"task_id": task["id"], "title": ""},
        headers=eng_headers,
    )
    assert r.status_code == 422


def test_progress_boundary_0_and_100(client, mgr_headers, eng_headers):
    users = _users(client, mgr_headers)
    pid, did = _seed(client, mgr_headers, "P-pct-bound")
    task = _task(client, mgr_headers, pid, did, users["eng_test"]["id"])
    r = client.post(
        "/api/test-manage/actions",
        json={"task_id": task["id"], "title": "pct", "publish": True},
        headers=eng_headers,
    )
    aid = r.json()["id"]
    for pct in (0, 100):
        r = client.put(
            f"/api/test-manage/actions/{aid}/daily-updates",
            json={"progress_percent": pct, "progress_note": "本日进展说明已填写完毕"},
            headers=eng_headers,
        )
        assert r.status_code == 200, r.text
        assert r.json()["progress_percent"] == pct


def test_progress_negative_422(client, mgr_headers, eng_headers):
    users = _users(client, mgr_headers)
    pid, did = _seed(client, mgr_headers, "P-pct-neg")
    task = _task(client, mgr_headers, pid, did, users["eng_test"]["id"])
    r = client.post(
        "/api/test-manage/actions",
        json={"task_id": task["id"], "title": "n", "publish": True},
        headers=eng_headers,
    )
    aid = r.json()["id"]
    r = client.put(
        f"/api/test-manage/actions/{aid}/daily-updates",
        json={"progress_percent": -1, "progress_note": "本日进展说明已填写完毕"},
        headers=eng_headers,
    )
    assert r.status_code == 422


def test_empty_correction_note_422(client, mgr_headers, eng_headers):
    users = _users(client, mgr_headers)
    pid, did = _seed(client, mgr_headers, "P-corr-empty")
    task = _task(client, mgr_headers, pid, did, users["eng_test"]["id"])
    r = client.post(
        "/api/test-manage/actions",
        json={"task_id": task["id"], "title": "c", "publish": True},
        headers=eng_headers,
    )
    aid = r.json()["id"]
    r = client.post(
        f"/api/test-manage/actions/{aid}/corrections",
        json={"note": ""},
        headers=eng_headers,
    )
    assert r.status_code == 422


def test_invalid_project_status_400(client, mgr_headers):
    pid, _ = _seed(client, mgr_headers, "P-bad-status")
    r = client.patch(
        f"/api/test-manage/projects/{pid}",
        json={"status": "flying"},
        headers=mgr_headers,
    )
    assert r.status_code == 400


def test_invalid_task_status_400(client, mgr_headers, eng_headers):
    users = _users(client, mgr_headers)
    pid, did = _seed(client, mgr_headers, "P-task-st")
    task = _task(client, mgr_headers, pid, did, users["eng_test"]["id"])
    r = client.patch(
        f"/api/test-manage/tasks/{task['id']}",
        json={"status": "weird"},
        headers=eng_headers,
    )
    assert r.status_code == 400


def test_task_status_rejects_draft_cancelled(client, mgr_headers, eng_headers):
    """Task 状态仅允许进行中 / 已完成。"""
    users = _users(client, mgr_headers)
    pid, did = _seed(client, mgr_headers, "P-task-st2")
    task = _task(client, mgr_headers, pid, did, users["eng_test"]["id"])
    for bad in ("draft", "cancelled"):
        r = client.patch(
            f"/api/test-manage/tasks/{task['id']}",
            json={"status": bad},
            headers=eng_headers,
        )
        assert r.status_code == 400, bad


def test_done_task_cannot_create_action(client, mgr_headers, eng_headers):
    """已完成 Task 不可再创建 Action。"""
    users = _users(client, mgr_headers)
    pid, did = _seed(client, mgr_headers, "P-done-act")
    task = _task(client, mgr_headers, pid, did, users["eng_test"]["id"])
    assert task.get("can_add_action") is True
    r = client.patch(
        f"/api/test-manage/tasks/{task['id']}",
        json={"status": "done"},
        headers=eng_headers,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "done"
    assert r.json()["can_add_action"] is False
    r = client.post(
        "/api/test-manage/actions",
        json={"task_id": task["id"], "title": "不应创建", "publish": False},
        headers=eng_headers,
    )
    assert r.status_code == 400
    assert "已完成" in r.json()["detail"]


def test_invalid_action_status_400(client, mgr_headers, eng_headers):
    users = _users(client, mgr_headers)
    pid, did = _seed(client, mgr_headers, "P-act-st")
    task = _task(client, mgr_headers, pid, did, users["eng_test"]["id"])
    r = client.post(
        "/api/test-manage/actions",
        json={"task_id": task["id"], "title": "s", "publish": False},
        headers=eng_headers,
    )
    aid = r.json()["id"]
    r = client.patch(
        f"/api/test-manage/actions/{aid}",
        json={"status": "flying"},
        headers=eng_headers,
    )
    assert r.status_code == 400


# ── 业务一致性异常 ───────────────────────────────────────────


def test_task_domain_project_mismatch_400(client, mgr_headers):
    users = _users(client, mgr_headers)
    pid1, did1 = _seed(client, mgr_headers, "P-mis-1")
    pid2, did2 = _seed(client, mgr_headers, "P-mis-2")
    r = client.post(
        "/api/test-manage/tasks",
        json={
            "project_id": pid1,
            "domain_id": did2,  # 属于 pid2
            "title": "错配",
            "lead_id": users["eng_test"]["id"],
        },
        headers=mgr_headers,
    )
    assert r.status_code == 400


def test_nonexistent_lead_user_400(client, mgr_headers):
    pid, did = _seed(client, mgr_headers, "P-bad-lead")
    r = client.post(
        "/api/test-manage/tasks",
        json={
            "project_id": pid,
            "domain_id": did,
            "title": "无此人",
            "lead_id": 999999,
        },
        headers=mgr_headers,
    )
    assert r.status_code == 400


def test_lead_not_duplicated_in_testers(client, mgr_headers):
    users = _users(client, mgr_headers)
    lead = users["eng_test"]["id"]
    pid, did = _seed(client, mgr_headers, "P-lead-dup")
    task = _task(
        client,
        mgr_headers,
        pid,
        did,
        lead,
        tester_ids=[lead, users["manager"]["id"]],
    )
    assert lead not in task["tester_ids"]
    assert users["manager"]["id"] in task["tester_ids"]


def test_daily_same_day_upsert_overwrites(client, mgr_headers, eng_headers):
    users = _users(client, mgr_headers)
    pid, did = _seed(client, mgr_headers, "P-upsert")
    task = _task(client, mgr_headers, pid, did, users["eng_test"]["id"])
    r = client.post(
        "/api/test-manage/actions",
        json={"task_id": task["id"], "title": "u", "publish": True},
        headers=eng_headers,
    )
    aid = r.json()["id"]
    r1 = client.put(
        f"/api/test-manage/actions/{aid}/daily-updates",
        json={"progress_percent": 20, "progress_note": "本日进展说明已填写完毕"},
        headers=eng_headers,
    )
    assert r1.status_code == 200
    id1 = r1.json()["id"]
    r2 = client.put(
        f"/api/test-manage/actions/{aid}/daily-updates",
        json={"progress_percent": 55, "progress_note": "本日进展说明已填写完毕"},
        headers=eng_headers,
    )
    assert r2.status_code == 200
    assert r2.json()["id"] == id1  # 同日更新同一条
    assert r2.json()["progress_percent"] == 55
    r = client.get(f"/api/test-manage/actions/{aid}", headers=eng_headers)
    assert r.json()["progress_percent"] == 55
    assert len(r.json()["daily_updates"]) == 1


def test_draft_action_cannot_correct(client, mgr_headers, eng_headers):
    """草稿不可追加更正说明。"""
    users = _users(client, mgr_headers)
    pid, did = _seed(client, mgr_headers, "P-draft-correct")
    task = _task(client, mgr_headers, pid, did, users["eng_test"]["id"])
    r = client.post(
        "/api/test-manage/actions",
        json={"task_id": task["id"], "title": "draft", "publish": False},
        headers=eng_headers,
    )
    aid = r.json()["id"]
    r = client.post(
        f"/api/test-manage/actions/{aid}/corrections",
        json={"note": "草稿不应更正"},
        headers=eng_headers,
    )
    assert r.status_code == 403


def test_done_action_cannot_daily(client, mgr_headers, eng_headers):
    """已完成 Action 不可再写日更。"""
    users = _users(client, mgr_headers)
    pid, did = _seed(client, mgr_headers, "P-done-daily")
    task = _task(client, mgr_headers, pid, did, users["eng_test"]["id"])
    r = client.post(
        "/api/test-manage/actions",
        json={"task_id": task["id"], "title": "done", "publish": True},
        headers=eng_headers,
    )
    aid = r.json()["id"]
    r = client.put(
        f"/api/test-manage/actions/{aid}/daily-updates",
        json={"progress_percent": 100, "progress_note": "本日进展说明已填写完毕"},
        headers=eng_headers,
    )
    assert r.status_code == 200
    r = client.patch(
        f"/api/test-manage/actions/{aid}",
        json={"status": "done"},
        headers=eng_headers,
    )
    assert r.status_code == 200
    r = client.get(f"/api/test-manage/actions/{aid}", headers=eng_headers)
    assert r.json()["can_daily"] is False
    r = client.put(
        f"/api/test-manage/actions/{aid}/daily-updates",
        json={"progress_percent": 100, "progress_note": "本日进展说明已填写完毕"},
        headers=eng_headers,
    )
    assert r.status_code == 403


def test_stranger_cannot_clone_candidates(client, mgr_headers, eng_headers, eng2_headers):
    users = _users(client, mgr_headers)
    pid, did = _seed(client, mgr_headers, "P-clone-deny")
    task = _task(client, mgr_headers, pid, did, users["eng_test"]["id"])
    r = client.get(
        f"/api/test-manage/tasks/{task['id']}/clone-candidates",
        headers=eng2_headers,
    )
    assert r.status_code == 403


def test_unauthenticated_board_401(client):
    r = client.get("/api/test-manage/board")
    assert r.status_code == 401


def test_week_boundary_one_second_around_wed18():
    just_before = datetime(2026, 7, 15, 17, 59, 59, tzinfo=TM_TZ)
    just_at = datetime(2026, 7, 15, 18, 0, 0, tzinfo=TM_TZ)
    just_after = datetime(2026, 7, 15, 18, 0, 1, tzinfo=TM_TZ)
    assert current_week_start(just_before) == datetime(2026, 7, 8, 18, 0, tzinfo=TM_TZ)
    assert current_week_start(just_at) == datetime(2026, 7, 15, 18, 0, tzinfo=TM_TZ)
    assert current_week_start(just_after) == datetime(2026, 7, 15, 18, 0, tzinfo=TM_TZ)


def test_action_default_owner_is_task_lead(client, mgr_headers, eng_headers):
    users = _users(client, mgr_headers)
    lead = users["eng_test"]["id"]
    pid, did = _seed(client, mgr_headers, "P-owner-default")
    task = _task(client, mgr_headers, pid, did, lead)
    r = client.post(
        "/api/test-manage/actions",
        json={"task_id": task["id"], "title": "默认负责人", "publish": True},
        headers=eng_headers,
    )
    assert r.status_code == 201
    assert r.json()["owner_id"] == lead


def test_board_excludes_cancelled_actions(client, mgr_headers, eng_headers):
    """历史 cancelled Action 不进看板（新操作已禁止取消，用 DB 写入存量）。"""
    from app.platform.database import SessionLocal
    from app.test_manage.models import TmAction

    users = _users(client, mgr_headers)
    pid, did = _seed(client, mgr_headers, "P-board-cxl")
    task = _task(client, mgr_headers, pid, did, users["eng_test"]["id"], title="BoardCxl")
    r = client.post(
        "/api/test-manage/actions",
        json={"task_id": task["id"], "title": "可见进行中", "publish": True},
        headers=eng_headers,
    )
    assert r.status_code == 201
    aid_ok = r.json()["id"]

    with SessionLocal() as db:
        cur = db.query(TmAction).filter(TmAction.id == aid_ok).first()
        cxl = TmAction(
            task_id=cur.task_id,
            project_id=cur.project_id,
            domain_id=cur.domain_id,
            week_start=cur.week_start,
            week_key=cur.week_key,
            title="历史取消不进板",
            owner_id=cur.owner_id,
            test_content="",
            environment="",
            status="cancelled",
            created_by=cur.created_by,
            published_at=cur.week_start,
            due_at=cur.due_at,
        )
        db.add(cxl)
        db.commit()
        aid_cxl = cxl.id

    r = client.get("/api/test-manage/board", headers=mgr_headers)
    hit = next((t for t in r.json()["tasks"] if t["task"]["id"] == task["id"]), None)
    assert hit is not None
    ids = {a["id"] for a in hit["actions"]}
    assert aid_ok in ids
    assert aid_cxl not in ids


def test_text_fields_max_1000_chars(client, mgr_headers, eng_headers):
    """非需求文本字段上限 1000（风险/说明/更正/测试内容等）。"""
    from app.test_manage.config import TEXT_FIELD_MAX_CHARS

    users = _users(client, mgr_headers)
    pid, did = _seed(client, mgr_headers, "P-maxlen")
    task = _task(client, mgr_headers, pid, did, users["eng_test"]["id"])
    too_long = "x" * (TEXT_FIELD_MAX_CHARS + 1)
    r = client.post(
        "/api/test-manage/actions",
        json={
            "task_id": task["id"],
            "title": "maxlen",
            "test_content": too_long,
            "publish": False,
        },
        headers=eng_headers,
    )
    assert r.status_code == 422

    r = client.post(
        "/api/test-manage/actions",
        json={"task_id": task["id"], "title": "ok", "publish": True},
        headers=eng_headers,
    )
    aid = r.json()["id"]
    r = client.put(
        f"/api/test-manage/actions/{aid}/daily-updates",
        json={"progress_percent": 10, "risk_blocker": too_long, "progress_note": "本日进展说明已填写完毕"},
        headers=eng_headers,
    )
    assert r.status_code == 422
    r = client.post(
        f"/api/test-manage/actions/{aid}/corrections",
        json={"note": too_long},
        headers=eng_headers,
    )
    assert r.status_code == 422
    r = client.put(
        f"/api/test-manage/actions/{aid}/daily-updates",
        json={"progress_percent": 10, "progress_note": too_long},
        headers=eng_headers,
    )
    assert r.status_code == 422
