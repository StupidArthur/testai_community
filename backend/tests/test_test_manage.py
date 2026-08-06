"""
test_manage 全覆盖自测：周界 / 权限 / Task·Action 生命周期 / 看板 / 克隆 / 日更。
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.platform.database import SessionLocal
from app.test_manage.config import TM_TZ
from app.test_manage.models import TmAction
from app.test_manage.week import (
    current_week_start,
    previous_week_start,
    week_end,
    week_key,
)


# ── 周界纯函数 ───────────────────────────────────────────────


def test_week_thu_in_current_window():
    thu = datetime(2026, 7, 16, 10, 0, tzinfo=TM_TZ)
    ws = current_week_start(thu)
    assert ws == datetime(2026, 7, 15, 17, 0, tzinfo=TM_TZ)
    assert week_end(ws) == datetime(2026, 7, 22, 17, 0, tzinfo=TM_TZ)
    assert week_key(ws) == "2026-07-15T17"


def test_week_wed_before_17_belongs_prev():
    wed = datetime(2026, 7, 15, 16, 59, tzinfo=TM_TZ)
    assert current_week_start(wed) == datetime(2026, 7, 8, 17, 0, tzinfo=TM_TZ)


def test_week_wed_at_17_starts_new():
    wed = datetime(2026, 7, 15, 17, 0, tzinfo=TM_TZ)
    assert current_week_start(wed) == datetime(2026, 7, 15, 17, 0, tzinfo=TM_TZ)


def test_week_monday_still_prev_window():
    """周一仍属上周三 17:00 开启的周。"""
    mon = datetime(2026, 7, 13, 12, 0, tzinfo=TM_TZ)  # 周一
    assert current_week_start(mon) == datetime(2026, 7, 8, 17, 0, tzinfo=TM_TZ)


def test_previous_week_start_fn():
    ws = datetime(2026, 7, 15, 17, 0, tzinfo=TM_TZ)
    assert previous_week_start(ws) == datetime(2026, 7, 8, 17, 0, tzinfo=TM_TZ)


# ── fixtures helpers ─────────────────────────────────────────


@pytest.fixture()
def mgr_headers(client):
    r = client.post("/api/auth/login", json={"username": "manager", "password": "123456"})
    assert r.status_code == 200, r.text
    assert r.json()["user"]["role"] == "Manager"
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def eng2_headers(client, auth_headers):
    """第二个工程师，用于「无关人员」权限断言。"""
    r = client.post(
        "/api/auth/add-user",
        json={"username": "eng_other", "password": "eng123456", "role": "Engineer"},
        headers=auth_headers,
    )
    if r.status_code == 200:
        token = r.json()["access_token"]
    else:
        r = client.post(
            "/api/auth/login",
            json={"username": "eng_other", "password": "eng123456"},
        )
        assert r.status_code == 200
        token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _users(client, headers):
    r = client.get("/api/test-manage/users", headers=headers)
    assert r.status_code == 200
    return {u["username"]: u for u in r.json()}


def _seed_project_domain(client, mgr_headers, name="TPT-SEED"):
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


def _seed_task(client, mgr_headers, project_id, domain_id, lead_id, tester_ids=None, title="Task-A"):
    r = client.post(
        "/api/test-manage/tasks",
        json={
            "project_id": project_id,
            "domain_id": domain_id,
            "title": title,
            "requirement": "需求正文",
            "lead_id": lead_id,
            "tester_ids": tester_ids or [],
            "publish": True,
        },
        headers=mgr_headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


# ── manager / auth ───────────────────────────────────────────


def test_users_endpoint_returns_usernames(client, mgr_headers):
    """前端选人依赖 username；不能只返回裸 id。"""
    r = client.get("/api/test-manage/users", headers=mgr_headers)
    assert r.status_code == 200, r.text
    rows = r.json()
    assert isinstance(rows, list) and len(rows) >= 1
    for u in rows:
        assert "id" in u and "username" in u
        assert isinstance(u["username"], str) and u["username"].strip()
        assert "real_name" in u


def test_admin_can_create_manager_role_user(client, auth_headers):
    """Admin 添加用户时应支持 role=Manager（曾被写成只能 Admin/Engineer）。"""
    r = client.post(
        "/api/auth/add-user",
        json={"username": "mgr_extra", "password": "12345678", "role": "Manager"},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["user"]["role"] == "Manager"


# ── Project / Domain ─────────────────────────────────────────


def test_eng_cannot_create_project_or_domain(client, eng_headers, mgr_headers):
    r = client.post(
        "/api/test-manage/projects", json={"name": "X"}, headers=eng_headers
    )
    assert r.status_code == 403
    pid, _ = _seed_project_domain(client, mgr_headers, "P-deny")
    r = client.post(
        f"/api/test-manage/projects/{pid}/domains",
        json={"name": "D"},
        headers=eng_headers,
    )
    assert r.status_code == 403


def test_duplicate_domain_name_rejected(client, mgr_headers):
    pid, _ = _seed_project_domain(client, mgr_headers, "P-dup")
    r = client.post(
        f"/api/test-manage/projects/{pid}/domains",
        json={"name": "Agent"},
        headers=mgr_headers,
    )
    assert r.status_code == 400


def test_project_archive(client, mgr_headers):
    pid, _ = _seed_project_domain(client, mgr_headers, "P-arch")
    r = client.patch(
        f"/api/test-manage/projects/{pid}",
        json={"status": "archived"},
        headers=mgr_headers,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "archived"
    r = client.get("/api/test-manage/projects", headers=mgr_headers)
    assert all(p["id"] != pid for p in r.json())


# ── Task 权限与日志 ──────────────────────────────────────────


def test_eng_cannot_create_task_but_lead_can_update(
    client, mgr_headers, eng_headers, eng2_headers
):
    users = _users(client, mgr_headers)
    pid, did = _seed_project_domain(client, mgr_headers, "P-task")
    r = client.post(
        "/api/test-manage/tasks",
        json={
            "project_id": pid,
            "domain_id": did,
            "title": "T",
            "lead_id": users["eng_test"]["id"],
            "publish": True,
        },
        headers=eng_headers,
    )
    assert r.status_code == 403

    task = _seed_task(
        client, mgr_headers, pid, did, users["eng_test"]["id"], title="LeadTask"
    )
    # 负责人可改
    r = client.patch(
        f"/api/test-manage/tasks/{task['id']}",
        json={"requirement": "新需求", "change_summary": "改需求"},
        headers=eng_headers,
    )
    assert r.status_code == 200
    # 无关人员不可改
    r = client.patch(
        f"/api/test-manage/tasks/{task['id']}",
        json={"requirement": "黑客"},
        headers=eng2_headers,
    )
    assert r.status_code == 403
    # 有更新日志
    r = client.get(f"/api/test-manage/tasks/{task['id']}", headers=eng_headers)
    assert len(r.json()["update_logs"]) >= 1


# ── Action 生命周期 ──────────────────────────────────────────


def test_action_draft_edit_then_publish_locks(
    client, mgr_headers, eng_headers, eng2_headers
):
    users = _users(client, mgr_headers)
    pid, did = _seed_project_domain(client, mgr_headers, "P-act")
    task = _seed_task(client, mgr_headers, pid, did, users["eng_test"]["id"])

    # 无关人不能建 Action
    r = client.post(
        "/api/test-manage/actions",
        json={"task_id": task["id"], "title": "偷建", "publish": False},
        headers=eng2_headers,
    )
    assert r.status_code == 403

    # 负责人建草稿
    r = client.post(
        "/api/test-manage/actions",
        json={
            "task_id": task["id"],
            "title": "草稿A",
            "test_content": "v1",
            "environment": "dev",
            "publish": False,
        },
        headers=eng_headers,
    )
    assert r.status_code == 201, r.text
    aid = r.json()["id"]
    assert r.json()["status"] == "draft"
    assert r.json()["can_edit_fields"] is True

    # 草稿可改
    r = client.patch(
        f"/api/test-manage/actions/{aid}",
        json={"test_content": "v2"},
        headers=eng_headers,
    )
    assert r.status_code == 200
    assert r.json()["test_content"] == "v2"

    # 发布
    r = client.patch(
        f"/api/test-manage/actions/{aid}",
        json={"status": "published"},
        headers=eng_headers,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "published"
    assert r.json()["can_edit_fields"] is False

    # 发布后改字段失败
    r = client.patch(
        f"/api/test-manage/actions/{aid}",
        json={"test_content": "v3"},
        headers=eng_headers,
    )
    assert r.status_code == 403

    # 更正说明 OK
    r = client.post(
        f"/api/test-manage/actions/{aid}/corrections",
        json={"note": "原 v2 笔误，应为 v2-fixed"},
        headers=eng_headers,
    )
    assert r.status_code == 201
    r = client.get(f"/api/test-manage/actions/{aid}", headers=eng_headers)
    assert len(r.json()["corrections"]) >= 1


def test_daily_update_permissions_and_progress_avg(
    client, mgr_headers, eng_headers, eng2_headers
):
    """B1：仅 Action owner 或 Admin/Manager 可日更；测试人员不能代写他人 Action。"""
    users = _users(client, mgr_headers)
    # 确保 eng_other 在用户表
    client.get("/api/test-manage/week", headers=eng2_headers)
    users = _users(client, mgr_headers)
    pid, did = _seed_project_domain(client, mgr_headers, "P-daily")
    task = _seed_task(
        client,
        mgr_headers,
        pid,
        did,
        users["eng_test"]["id"],
        tester_ids=[users["eng_other"]["id"]],
    )
    r = client.post(
        "/api/test-manage/actions",
        json={
            "task_id": task["id"],
            "title": "日更A",
            "owner_id": users["eng_test"]["id"],
            "publish": True,
        },
        headers=eng_headers,
    )
    assert r.status_code == 201, r.text
    aid = r.json()["id"]

    # 无关人不能日更
    r = client.put(
        f"/api/test-manage/actions/{aid}/daily-updates",
        json={"progress_percent": 10, "progress_note": "本日进展说明已填写完毕"},
        headers=eng2_headers,
    )
    assert r.status_code == 403

    # Task 测试人员（非 owner）也不能代写
    # eng2 即 eng_other
    r = client.put(
        f"/api/test-manage/actions/{aid}/daily-updates",
        json={"progress_percent": 20, "progress_note": "本日进展说明已填写完毕"},
        headers=eng2_headers,
    )
    assert r.status_code == 403

    # 负责人日更 40（有风险）
    r = client.put(
        f"/api/test-manage/actions/{aid}/daily-updates",
        json={
            "progress_percent": 40,
            "risk_blocker": "卡接口",
            "progress_note": "本日进展说明已填写完毕",
        },
        headers=eng_headers,
    )
    assert r.status_code == 200

    # Admin/Manager 同日覆盖 60 且清空风险 → 进度 60，风险已解决
    r = client.put(
        f"/api/test-manage/actions/{aid}/daily-updates",
        json={
            "progress_percent": 60,
            "risk_blocker": "",
            "progress_note": "本日进展说明已填写完毕",
        },
        headers=mgr_headers,
    )
    assert r.status_code == 200

    r = client.get(f"/api/test-manage/actions/{aid}", headers=eng_headers)
    assert r.json()["progress_percent"] == 60
    assert (r.json()["latest_risk"] or "") == ""


def test_action_owner_must_be_task_participant(client, mgr_headers, eng_headers, eng2_headers):
    """A1：owner 必须是 lead 或 tester；B1：非 owner 的 Task lead 不可代写日更。"""
    users = _users(client, mgr_headers)
    client.get("/api/test-manage/week", headers=eng2_headers)
    users = _users(client, mgr_headers)
    pid, did = _seed_project_domain(client, mgr_headers, "P-owner-cand")
    task = _seed_task(client, mgr_headers, pid, did, users["eng_test"]["id"])
    # eng_other 不在参与者中
    r = client.post(
        "/api/test-manage/actions",
        json={
            "task_id": task["id"],
            "title": "非法负责人",
            "owner_id": users["eng_other"]["id"],
            "publish": False,
        },
        headers=eng_headers,
    )
    assert r.status_code == 400, r.text

    # 合法：tester 可作为 owner
    task2 = _seed_task(
        client,
        mgr_headers,
        pid,
        did,
        users["eng_test"]["id"],
        tester_ids=[users["eng_other"]["id"]],
        title="Task-cand-ok",
    )
    r = client.post(
        "/api/test-manage/actions",
        json={
            "task_id": task2["id"],
            "title": "合法负责人",
            "owner_id": users["eng_other"]["id"],
            "publish": True,
        },
        headers=eng_headers,
    )
    assert r.status_code == 201, r.text
    aid = r.json()["id"]
    assert r.json()["owner_id"] == users["eng_other"]["id"]
    # owner 本人可日更
    r = client.put(
        f"/api/test-manage/actions/{aid}/daily-updates",
        json={"progress_percent": 30, "progress_note": "本日进展说明已填写完毕"},
        headers=eng2_headers,
    )
    assert r.status_code == 200
    # Task lead（非 owner）不可日更
    r = client.put(
        f"/api/test-manage/actions/{aid}/daily-updates",
        json={"progress_percent": 10, "progress_note": "本日进展说明已填写完毕"},
        headers=eng_headers,
    )
    assert r.status_code == 403


def test_clone_resets_progress_and_links_source(client, mgr_headers, eng_headers):
    users = _users(client, mgr_headers)
    pid, did = _seed_project_domain(client, mgr_headers, "P-clone")
    task = _seed_task(client, mgr_headers, pid, did, users["eng_test"]["id"])
    r = client.post(
        "/api/test-manage/actions",
        json={
            "task_id": task["id"],
            "title": "上周遗留",
            "test_content": "内容",
            "publish": True,
        },
        headers=eng_headers,
    )
    src_id = r.json()["id"]
    client.put(
        f"/api/test-manage/actions/{src_id}/daily-updates",
        json={"progress_percent": 80, "progress_note": "本日进展说明已填写完毕"},
        headers=eng_headers,
    )

    # 把源 Action 改到「上周」week_key，才能出现在 clone-candidates
    prev = previous_week_start()
    with SessionLocal() as db:
        row = db.query(TmAction).filter(TmAction.id == src_id).first()
        row.week_start = prev
        row.week_key = week_key(prev)
        row.due_at = week_end(prev)
        db.commit()

    r = client.get(
        f"/api/test-manage/tasks/{task['id']}/clone-candidates",
        headers=eng_headers,
    )
    assert r.status_code == 200
    assert any(a["id"] == src_id for a in r.json())

    r = client.post(
        f"/api/test-manage/actions/{src_id}/clone",
        json={"publish": False},
        headers=eng_headers,
    )
    assert r.status_code == 201, r.text
    cloned = r.json()
    assert cloned["source_action_id"] == src_id
    assert cloned["status"] == "draft"
    assert cloned["progress_percent"] == 0
    assert cloned["test_content"] == "内容"
    assert cloned["week_key"] == week_key(current_week_start())


def test_done_task_blocks_new_action(client, mgr_headers, eng_headers):
    """已完成 Task 不可再创建 Action。"""
    users = _users(client, mgr_headers)
    pid, did = _seed_project_domain(client, mgr_headers, "P-done-block")
    task = _seed_task(client, mgr_headers, pid, did, users["eng_test"]["id"])
    r = client.patch(
        f"/api/test-manage/tasks/{task['id']}",
        json={"status": "done"},
        headers=mgr_headers,
    )
    assert r.status_code == 200
    assert r.json()["can_add_action"] is False
    r = client.post(
        "/api/test-manage/actions",
        json={"task_id": task["id"], "title": "不应创建"},
        headers=eng_headers,
    )
    assert r.status_code == 400


# ── 看板 ─────────────────────────────────────────────────────


def test_board_week_task_aggregation_and_project_filter(
    client, mgr_headers, eng_headers, auth_headers
):
    users = _users(client, mgr_headers)
    pid1, did1 = _seed_project_domain(client, mgr_headers, "P-board-1")
    pid2, did2 = _seed_project_domain(client, mgr_headers, "P-board-2")
    t1 = _seed_task(client, mgr_headers, pid1, did1, users["eng_test"]["id"], title="T1")
    t2 = _seed_task(client, mgr_headers, pid2, did2, users["eng_test"]["id"], title="T2")

    r = client.post(
        "/api/test-manage/actions",
        json={"task_id": t1["id"], "title": "A1", "publish": True},
        headers=eng_headers,
    )
    a1 = r.json()["id"]
    client.put(
        f"/api/test-manage/actions/{a1}/daily-updates",
        json={"progress_percent": 30, "risk_blocker": "风险甲", "progress_note": "本日进展说明已填写完毕"},
        headers=eng_headers,
    )
    client.post(
        "/api/test-manage/actions",
        json={"task_id": t2["id"], "title": "A2", "publish": True},
        headers=eng_headers,
    )

    r = client.get("/api/test-manage/board", headers=auth_headers)
    assert r.status_code == 200
    board = r.json()
    assert board["week_key"] == week_key(current_week_start())
    ids = {t["task"]["id"] for t in board["tasks"]}
    assert t1["id"] in ids and t2["id"] in ids
    hit = next(t for t in board["tasks"] if t["task"]["id"] == t1["id"])
    assert "风险甲" in hit["risks"]
    # 页顶本周汇总
    summary = board["summary"]
    assert summary["task_count"] >= 2
    assert summary["action_count"] >= 2
    assert summary["risk_action_count"] >= 1
    assert summary["published_count"] >= 2
    assert 0 <= summary["progress_avg"] <= 100

    r = client.get(
        "/api/test-manage/board",
        params={"project_id": pid1},
        headers=auth_headers,
    )
    assert r.status_code == 200
    ids = {t["task"]["id"] for t in r.json()["tasks"]}
    assert t1["id"] in ids
    assert t2["id"] not in ids


def test_mine_lists_only_owned_actions(client, mgr_headers, eng_headers, eng2_headers):
    """「我的 Action」仅含 owner=自己；Task 测试人员看不到他人负责的 Action。"""
    users = _users(client, mgr_headers)
    client.get("/api/test-manage/week", headers=eng2_headers)
    users = _users(client, mgr_headers)
    pid, did = _seed_project_domain(client, mgr_headers, "P-mine")
    # lead=eng_test, tester=eng_other；Action 负责人 eng_test
    task = _seed_task(
        client,
        mgr_headers,
        pid,
        did,
        users["eng_test"]["id"],
        tester_ids=[users["eng_other"]["id"]],
    )
    r = client.post(
        "/api/test-manage/actions",
        json={
            "task_id": task["id"],
            "title": "eng_test的Action",
            "owner_id": users["eng_test"]["id"],
            "publish": True,
        },
        headers=eng_headers,
    )
    assert r.status_code == 201, r.text
    aid = r.json()["id"]

    r = client.get("/api/test-manage/actions/mine", headers=eng_headers)
    assert any(a["id"] == aid for a in r.json())

    # 测试人员 eng_other 不应在「我的」里看到该 Action
    r = client.get("/api/test-manage/actions/mine", headers=eng2_headers)
    assert all(a["id"] != aid for a in r.json())

    # eng_other 自己的 Action 会出现在自己的「我的」
    r = client.post(
        "/api/test-manage/actions",
        json={
            "task_id": task["id"],
            "title": "eng_other的Action",
            "owner_id": users["eng_other"]["id"],
            "publish": True,
        },
        headers=eng_headers,
    )
    assert r.status_code == 201, r.text
    aid2 = r.json()["id"]
    r = client.get("/api/test-manage/actions/mine", headers=eng2_headers)
    assert any(a["id"] == aid2 for a in r.json())
    assert all(a["id"] != aid for a in r.json())


def test_draft_action_cannot_daily_or_correct(client, mgr_headers, eng_headers):
    users = _users(client, mgr_headers)
    pid, did = _seed_project_domain(client, mgr_headers, "P-draft-daily")
    task = _seed_task(client, mgr_headers, pid, did, users["eng_test"]["id"])
    r = client.post(
        "/api/test-manage/actions",
        json={"task_id": task["id"], "title": "未发布", "publish": False},
        headers=eng_headers,
    )
    aid = r.json()["id"]
    r = client.put(
        f"/api/test-manage/actions/{aid}/daily-updates",
        json={"progress_percent": 10, "progress_note": "本日进展说明已填写完毕"},
        headers=eng_headers,
    )
    assert r.status_code == 403
    r = client.post(
        f"/api/test-manage/actions/{aid}/corrections",
        json={"note": "不应允许"},
        headers=eng_headers,
    )
    assert r.status_code == 403


def test_invalid_progress_percent_rejected(client, mgr_headers, eng_headers):
    users = _users(client, mgr_headers)
    pid, did = _seed_project_domain(client, mgr_headers, "P-pct")
    task = _seed_task(client, mgr_headers, pid, did, users["eng_test"]["id"])
    r = client.post(
        "/api/test-manage/actions",
        json={"task_id": task["id"], "title": "pct", "publish": True},
        headers=eng_headers,
    )
    aid = r.json()["id"]
    r = client.put(
        f"/api/test-manage/actions/{aid}/daily-updates",
        json={"progress_percent": 150, "progress_note": "本日进展说明已填写完毕"},
        headers=eng_headers,
    )
    assert r.status_code == 422


def test_end_to_end_happy_path(client, mgr_headers, eng_headers, auth_headers):
    """冒烟：manager 建树 → 负责人发 Action → 日更 → 看板可见。"""
    users = _users(client, mgr_headers)
    pid, did = _seed_project_domain(client, mgr_headers, "P-e2e")
    task = _seed_task(
        client,
        mgr_headers,
        pid,
        did,
        users["eng_test"]["id"],
        tester_ids=[users["manager"]["id"]],
        title="E2E-Task",
    )
    r = client.post(
        "/api/test-manage/actions",
        json={
            "task_id": task["id"],
            "title": "E2E-Action",
            "test_content": "测登录",
            "environment": "qa",
            "publish": True,
        },
        headers=eng_headers,
    )
    assert r.status_code == 201
    aid = r.json()["id"]
    client.put(
        f"/api/test-manage/actions/{aid}/daily-updates",
        json={"progress_percent": 70, "progress_note": "本日进展说明已填写完毕"},
        headers=eng_headers,
    )
    r = client.get("/api/test-manage/board", headers=auth_headers)
    hit = next(t for t in r.json()["tasks"] if t["task"]["id"] == task["id"])
    assert hit["week_progress_avg"] == 70
    assert any(a["id"] == aid for a in hit["actions"])
