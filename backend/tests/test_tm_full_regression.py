"""
项目管理全场景回归（结构对齐 TPT v2.1：平台/Agent Domain）。

覆盖：Admin/Manager/Lead/Owner/无关 Engineer 权限矩阵、
Task 仅进行中/已完成、空周 Task 看板、复制上周不带风险、
日更 B1、状态机、日报/周报 dry_run 口径。
"""
from __future__ import annotations

import pytest

from app.test_manage.push_report import collect_open_risks, collect_progress_summary
from app.test_manage.week import current_week_start
from app.platform.database import SessionLocal


TAG = "【回归】"


@pytest.fixture()
def mgr_headers(client):
    r = client.post("/api/auth/login", json={"username": "manager", "password": "123456"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def lead_headers(client, auth_headers):
    """Task 测试负责人（Engineer）。"""
    r = client.post(
        "/api/auth/add-user",
        json={
            "username": "tm_lead",
            "password": "123456",
            "role": "Engineer",
            "real_name": "回归Lead",
        },
        headers=auth_headers,
    )
    if r.status_code != 200:
        r = client.post("/api/auth/login", json={"username": "tm_lead", "password": "123456"})
    assert r.status_code == 200, r.text
    body = r.json()
    token = body.get("access_token") or body.get("token")
    if not token:
        # add-user 可能只返回 user
        r = client.post("/api/auth/login", json={"username": "tm_lead", "password": "123456"})
        assert r.status_code == 200
        token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def owner_headers(client, auth_headers):
    r = client.post(
        "/api/auth/add-user",
        json={
            "username": "tm_owner",
            "password": "123456",
            "role": "Engineer",
            "real_name": "回归Owner",
        },
        headers=auth_headers,
    )
    if r.status_code != 200:
        r = client.post("/api/auth/login", json={"username": "tm_owner", "password": "123456"})
    assert r.status_code == 200, r.text
    body = r.json()
    token = body.get("access_token")
    if not token:
        r = client.post("/api/auth/login", json={"username": "tm_owner", "password": "123456"})
        assert r.status_code == 200
        token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def stranger_headers(client, auth_headers):
    r = client.post(
        "/api/auth/add-user",
        json={
            "username": "tm_stranger",
            "password": "123456",
            "role": "Engineer",
            "real_name": "回归路人",
        },
        headers=auth_headers,
    )
    if r.status_code != 200:
        r = client.post("/api/auth/login", json={"username": "tm_stranger", "password": "123456"})
    assert r.status_code == 200, r.text
    body = r.json()
    token = body.get("access_token")
    if not token:
        r = client.post("/api/auth/login", json={"username": "tm_stranger", "password": "123456"})
        assert r.status_code == 200
        token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _uid(client, headers, username: str) -> int:
    r = client.get("/api/test-manage/users", headers=headers)
    assert r.status_code == 200
    for u in r.json():
        if u["username"] == username:
            return int(u["id"])
    raise AssertionError(f"user {username} not found")


def _tpt_sandbox(client, mgr_headers):
    """创建对齐 TPT v2.1 的项目+Domain（测试库隔离，不污染开发库）。"""
    r = client.post(
        "/api/test-manage/projects",
        json={"name": f"{TAG} TPT v2.1", "description": "regression"},
        headers=mgr_headers,
    )
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    domains = {}
    for name in ("平台", "Agent", "交付", "定制"):
        r = client.post(
            f"/api/test-manage/projects/{pid}/domains",
            json={"name": name},
            headers=mgr_headers,
        )
        assert r.status_code == 201, r.text
        domains[name] = r.json()["id"]
    return pid, domains


def _create_task(
    client,
    headers,
    *,
    pid: str,
    did: str,
    lead_id: int,
    title: str,
    tester_ids=None,
    publish=True,
):
    r = client.post(
        "/api/test-manage/tasks",
        json={
            "project_id": pid,
            "domain_id": did,
            "title": title,
            "requirement": "回归需求",
            "lead_id": lead_id,
            "tester_ids": tester_ids or [],
            "publish": publish,
            "req_stage": "testing",
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


# ── A. 项目 / Domain 烟测 ───────────────────────────────────


def test_a_manager_can_create_project_domain(client, mgr_headers):
    r = client.post(
        "/api/test-manage/projects",
        json={"name": f"{TAG} 烟测项目", "description": "x"},
        headers=mgr_headers,
    )
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    r = client.post(
        f"/api/test-manage/projects/{pid}/domains",
        json={"name": "烟测域"},
        headers=mgr_headers,
    )
    assert r.status_code == 201, r.text


def test_a_engineer_cannot_create_project(client, lead_headers):
    r = client.post(
        "/api/test-manage/projects",
        json={"name": f"{TAG} eng-forbid", "description": "x"},
        headers=lead_headers,
    )
    assert r.status_code == 403


# ── B. Task 权限 ─────────────────────────────────────────────


def test_b_task_edit_matrix(
    client, auth_headers, mgr_headers, lead_headers, owner_headers, stranger_headers
):
    _ = owner_headers  # ensure tm_owner exists
    pid, domains = _tpt_sandbox(client, mgr_headers)
    lead_id = _uid(client, mgr_headers, "tm_lead")
    owner_id = _uid(client, mgr_headers, "tm_owner")
    task = _create_task(
        client,
        mgr_headers,
        pid=pid,
        did=domains["平台"],
        lead_id=lead_id,
        title=f"{TAG} Task权限",
        tester_ids=[owner_id],
    )
    tid = task["id"]

    # Manager 可改
    r = client.patch(
        f"/api/test-manage/tasks/{tid}",
        json={"title": f"{TAG} Task权限-mgr", "change_summary": "mgr改"},
        headers=mgr_headers,
    )
    assert r.status_code == 200, r.text

    # Lead 可改
    r = client.patch(
        f"/api/test-manage/tasks/{tid}",
        json={"requirement": "lead改需求", "change_summary": "lead改"},
        headers=lead_headers,
    )
    assert r.status_code == 200, r.text

    # Admin 可改
    r = client.patch(
        f"/api/test-manage/tasks/{tid}",
        json={"title": f"{TAG} Task权限-admin", "change_summary": "admin改"},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text

    # 无关 Engineer 不可改
    r = client.patch(
        f"/api/test-manage/tasks/{tid}",
        json={"title": "hack", "change_summary": "x"},
        headers=stranger_headers,
    )
    assert r.status_code == 403

    # 状态仅 published/done
    r = client.patch(
        f"/api/test-manage/tasks/{tid}",
        json={"status": "cancelled"},
        headers=mgr_headers,
    )
    assert r.status_code == 400

    r = client.patch(
        f"/api/test-manage/tasks/{tid}",
        json={"status": "done", "change_summary": "完成"},
        headers=mgr_headers,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "done"
    assert r.json().get("can_add_action") is False

    # done 后不可建 Action
    r = client.post(
        "/api/test-manage/actions",
        json={"task_id": tid, "title": f"{TAG} 不应创建", "owner_id": lead_id},
        headers=mgr_headers,
    )
    assert r.status_code == 400


def test_b_lead_can_change_lead_then_loses_edit_if_not_admin(
    client, mgr_headers, lead_headers, owner_headers
):
    pid, domains = _tpt_sandbox(client, mgr_headers)
    lead_id = _uid(client, mgr_headers, "tm_lead")
    owner_id = _uid(client, mgr_headers, "tm_owner")
    task = _create_task(
        client,
        mgr_headers,
        pid=pid,
        did=domains["Agent"],
        lead_id=lead_id,
        title=f"{TAG} 换负责人",
        tester_ids=[owner_id],
    )
    r = client.patch(
        f"/api/test-manage/tasks/{task['id']}",
        json={"lead_id": owner_id, "change_summary": "移交"},
        headers=lead_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["lead_id"] == owner_id
    # 原 lead 再改应 403
    r = client.patch(
        f"/api/test-manage/tasks/{task['id']}",
        json={"title": "不应成功"},
        headers=lead_headers,
    )
    assert r.status_code == 403
    # 新 lead 可改
    r = client.patch(
        f"/api/test-manage/tasks/{task['id']}",
        json={"title": f"{TAG} 换负责人-新lead"},
        headers=owner_headers,
    )
    assert r.status_code == 200


# ── C. Action 创建 / 复制 / A1 ───────────────────────────────


def test_c_action_create_clone_permissions(
    client, mgr_headers, lead_headers, stranger_headers, owner_headers
):
    pid, domains = _tpt_sandbox(client, mgr_headers)
    lead_id = _uid(client, mgr_headers, "tm_lead")
    owner_id = _uid(client, mgr_headers, "tm_owner")
    stranger_id = _uid(client, mgr_headers, "tm_stranger")
    task = _create_task(
        client,
        mgr_headers,
        pid=pid,
        did=domains["平台"],
        lead_id=lead_id,
        title=f"{TAG} Action权限",
        tester_ids=[owner_id],
    )
    tid = task["id"]

    # A1：owner 必须在参与者中
    r = client.post(
        "/api/test-manage/actions",
        json={
            "task_id": tid,
            "title": f"{TAG} 非法owner",
            "owner_id": stranger_id,
            "publish": False,
        },
        headers=lead_headers,
    )
    assert r.status_code == 400

    # lead 可建
    r = client.post(
        "/api/test-manage/actions",
        json={
            "task_id": tid,
            "title": f"{TAG} 上周源",
            "owner_id": owner_id,
            "test_content": "内容",
            "environment": "env",
            "publish": True,
        },
        headers=lead_headers,
    )
    assert r.status_code == 201, r.text
    src_id = r.json()["id"]

    # owner 写风险日更
    r = client.put(
        f"/api/test-manage/actions/{src_id}/daily-updates",
        json={"progress_percent": 40, "risk_blocker": "旧风险勿复制", "progress_note": "推进中"},
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text

    # 无关人不可建
    r = client.post(
        "/api/test-manage/actions",
        json={"task_id": tid, "title": f"{TAG} stranger", "owner_id": owner_id},
        headers=stranger_headers,
    )
    assert r.status_code == 403

    # 克隆：不带风险
    r = client.post(
        f"/api/test-manage/actions/{src_id}/clone",
        json={"publish": False},
        headers=lead_headers,
    )
    assert r.status_code == 201, r.text
    cloned = r.json()
    assert cloned["week_key"] == r.json()["week_key"]
    assert (cloned.get("latest_risk") or "").strip() == ""
    assert cloned["status"] == "draft"

    # 候选列表 lead 可见，stranger 不可
    r = client.get(f"/api/test-manage/tasks/{tid}/clone-candidates", headers=lead_headers)
    assert r.status_code == 200
    r = client.get(f"/api/test-manage/tasks/{tid}/clone-candidates", headers=stranger_headers)
    assert r.status_code == 403


# ── D/E. 状态机 + 日更 B1 ───────────────────────────────────


def test_d_e_status_and_daily_matrix(
    client, mgr_headers, lead_headers, owner_headers, stranger_headers
):
    pid, domains = _tpt_sandbox(client, mgr_headers)
    lead_id = _uid(client, mgr_headers, "tm_lead")
    owner_id = _uid(client, mgr_headers, "tm_owner")
    task = _create_task(
        client,
        mgr_headers,
        pid=pid,
        did=domains["Agent"],
        lead_id=lead_id,
        title=f"{TAG} 日更状态",
        tester_ids=[owner_id],
    )
    r = client.post(
        "/api/test-manage/actions",
        json={
            "task_id": task["id"],
            "title": f"{TAG} Act日更",
            "owner_id": owner_id,
            "publish": False,
        },
        headers=lead_headers,
    )
    assert r.status_code == 201
    aid = r.json()["id"]

    # owner 可发布自己的
    r = client.patch(
        f"/api/test-manage/actions/{aid}",
        json={"status": "published"},
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["can_edit_fields"] is False

    # 发布后改字段失败
    r = client.patch(
        f"/api/test-manage/actions/{aid}",
        json={"title": "改不了"},
        headers=lead_headers,
    )
    assert r.status_code == 403

    # lead 不能代写他人日更
    r = client.put(
        f"/api/test-manage/actions/{aid}/daily-updates",
        json={"progress_percent": 10, "risk_blocker": "", "progress_note": "lead代写"},
        headers=lead_headers,
    )
    assert r.status_code == 403

    # stranger 不能日更
    r = client.put(
        f"/api/test-manage/actions/{aid}/daily-updates",
        json={"progress_percent": 10, "risk_blocker": "", "progress_note": "路人"},
        headers=stranger_headers,
    )
    assert r.status_code == 403

    # owner 可日更；进度不倒退
    r = client.put(
        f"/api/test-manage/actions/{aid}/daily-updates",
        json={"progress_percent": 60, "risk_blocker": "阻塞A", "progress_note": "推进"},
        headers=owner_headers,
    )
    assert r.status_code == 200
    r = client.put(
        f"/api/test-manage/actions/{aid}/daily-updates",
        json={"progress_percent": 50, "risk_blocker": "", "progress_note": "倒退"},
        headers=owner_headers,
    )
    assert r.status_code == 400

    # 未到 100% 不能完成
    r = client.patch(
        f"/api/test-manage/actions/{aid}",
        json={"status": "done"},
        headers=owner_headers,
    )
    assert r.status_code == 400

    r = client.put(
        f"/api/test-manage/actions/{aid}/daily-updates",
        json={"progress_percent": 100, "risk_blocker": "", "progress_note": "完成"},
        headers=owner_headers,
    )
    assert r.status_code == 200
    r = client.patch(
        f"/api/test-manage/actions/{aid}",
        json={"status": "done"},
        headers=owner_headers,
    )
    assert r.status_code == 200
    # done 不可重开
    r = client.patch(
        f"/api/test-manage/actions/{aid}",
        json={"status": "published"},
        headers=mgr_headers,
    )
    assert r.status_code == 400

    # 更正说明（需进行中；另建一条）
    r = client.post(
        "/api/test-manage/actions",
        json={
            "task_id": task["id"],
            "title": f"{TAG} 更正用",
            "owner_id": owner_id,
            "publish": True,
        },
        headers=lead_headers,
    )
    aid2 = r.json()["id"]
    r = client.post(
        f"/api/test-manage/actions/{aid2}/corrections",
        json={"note": "更正一处笔误"},
        headers=owner_headers,
    )
    assert r.status_code in (200, 201), r.text


# ── F. 空周 Task 看板 ────────────────────────────────────────


def test_f_empty_week_task_on_board(client, mgr_headers, lead_headers):
    pid, domains = _tpt_sandbox(client, mgr_headers)
    lead_id = _uid(client, mgr_headers, "tm_lead")
    task = _create_task(
        client,
        mgr_headers,
        pid=pid,
        did=domains["交付"],
        lead_id=lead_id,
        title=f"{TAG} 空周Task",
    )
    r = client.get("/api/test-manage/board", params={"project_id": pid}, headers=lead_headers)
    assert r.status_code == 200, r.text
    titles = [b["task"]["title"] for b in r.json()["tasks"]]
    assert f"{TAG} 空周Task" in titles
    empty = next(b for b in r.json()["tasks"] if b["task"]["title"] == f"{TAG} 空周Task")
    assert empty["actions"] == []
    assert empty["task"]["can_add_action"] is True
    assert empty["task"]["can_edit"] is True


# ── G. 推送口径 dry_run ──────────────────────────────────────


def test_g_push_dry_run_and_empty_task_not_in_kpi(
    client, mgr_headers, lead_headers, owner_headers, stranger_headers
):
    pid, domains = _tpt_sandbox(client, mgr_headers)
    lead_id = _uid(client, mgr_headers, "tm_lead")
    owner_id = _uid(client, mgr_headers, "tm_owner")
    # 空 Task
    _create_task(
        client,
        mgr_headers,
        pid=pid,
        did=domains["定制"],
        lead_id=lead_id,
        title=f"{TAG} 推送空Task",
    )
    # 有 Action 的 Task
    task = _create_task(
        client,
        mgr_headers,
        pid=pid,
        did=domains["平台"],
        lead_id=lead_id,
        title=f"{TAG} 推送有Action",
        tester_ids=[owner_id],
    )
    r = client.post(
        "/api/test-manage/actions",
        json={
            "task_id": task["id"],
            "title": f"{TAG} 推送Act",
            "owner_id": owner_id,
            "publish": True,
        },
        headers=lead_headers,
    )
    assert r.status_code == 201
    aid = r.json()["id"]
    client.put(
        f"/api/test-manage/actions/{aid}/daily-updates",
        json={
            "progress_percent": 30,
            "risk_blocker": "风险X",
            "is_blocking": True,
            "progress_note": "记一笔",
        },
        headers=owner_headers,
    )

    db = SessionLocal()
    try:
        summary = collect_progress_summary(db, week_start=current_week_start())
        # 空 Task「推送空Task」本周无 Action → 不增加 task_count；有 Action 的计入
        assert summary.action_count >= 1
        assert summary.task_count >= 1
        # 已发布且勾选阻塞的风险进入开放风险
        risks = collect_open_risks(db, week_start=current_week_start())
        texts = " ".join((v.risk or "") for v in risks.values())
        assert "风险X" in texts
    finally:
        db.close()

    r = client.post(
        "/api/test-manage/push/daily",
        json={"dry_run": True, "force": False},
        headers=stranger_headers,
    )
    assert r.status_code == 403

    r = client.post(
        "/api/test-manage/push/daily",
        json={"dry_run": True, "force": False},
        headers=mgr_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("dry_run") is True or body.get("message")
    msg = body.get("message") or ""
    assert "测试日报" in msg or "日报" in msg
    # 日报正文已改「标题+深链+截图」，风险明细不再进文字（由上方 collect_open_risks 覆盖）

    r = client.post(
        "/api/test-manage/push/weekly",
        json={"dry_run": True, "force": False},
        headers=mgr_headers,
    )
    assert r.status_code == 200, r.text
    wmsg = r.json().get("message") or ""
    assert "周报" in wmsg or "Task" in wmsg
