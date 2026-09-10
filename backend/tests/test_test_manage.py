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
            "module": "默认模块",
            "lead_id": lead_id,
            "tester_ids": tester_ids or [],
            "publish": True,
            "req_stage": "testing",
        },
        headers=mgr_headers,
    )
    assert r.status_code == 201, r.text
    task = r.json()
    # 自动带一个默认子需求，便于测试创建 Action（subtask_name 必填）
    _seed_subtask(client, mgr_headers, task["id"], DEFAULT_SUBTASK_NAME, "默认子需求内容")
    return task


DEFAULT_SUBTASK_NAME = "默认子需求"


def _seed_subtask(client, headers, task_id, name=DEFAULT_SUBTASK_NAME, content=""):
    r = client.post(
        f"/api/test-manage/tasks/{task_id}/subtasks",
        json={"name": name, "content": content},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


def _create_action(client, headers, task_id, title, *, publish=True, subtask_name=None,
                   owner_id=None, **extra):
    """统一封装 Action 创建：自动补 subtask_name（必填）。"""
    payload = {
        "task_id": task_id,
        "title": title,
        "subtask_name": subtask_name or DEFAULT_SUBTASK_NAME,
        "publish": publish,
    }
    if owner_id is not None:
        payload["owner_id"] = owner_id
    payload.update(extra)
    r = client.post("/api/test-manage/actions", json=payload, headers=headers)
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
            "module": "默认模块",
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

    # 创建权限已放开：所有角色（含无关工程师）可建 Action
    r = client.post(
        "/api/test-manage/actions",
        json={"task_id": task["id"], "title": "偷建", "subtask_name": DEFAULT_SUBTASK_NAME, "publish": False},
        headers=eng2_headers,
    )
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "draft"

    # 负责人建草稿
    r = client.post(
        "/api/test-manage/actions",
        json={
            "task_id": task["id"],
            "title": "草稿A",
            "subtask_name": DEFAULT_SUBTASK_NAME,
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
            "subtask_name": DEFAULT_SUBTASK_NAME,
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


def test_action_owner_can_be_any_user(client, mgr_headers, eng_headers, eng2_headers):
    """A1（已放宽）：owner 可为任意用户；B1：非 owner 的 Task lead 不可代写日更。"""
    users = _users(client, mgr_headers)
    client.get("/api/test-manage/week", headers=eng2_headers)
    users = _users(client, mgr_headers)
    pid, did = _seed_project_domain(client, mgr_headers, "P-owner-cand")
    task = _seed_task(client, mgr_headers, pid, did, users["eng_test"]["id"])
    # eng_other 不在参与者中，但按新规则允许作为 owner
    r = client.post(
        "/api/test-manage/actions",
        json={
            "task_id": task["id"],
            "title": "非参与者负责人",
            "subtask_name": DEFAULT_SUBTASK_NAME,
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
        json={"task_id": task["id"], "title": "不应创建", "subtask_name": DEFAULT_SUBTASK_NAME},
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
        json={"task_id": t1["id"], "title": "A1", "subtask_name": DEFAULT_SUBTASK_NAME, "publish": True},
        headers=eng_headers,
    )
    a1 = r.json()["id"]
    client.put(
        f"/api/test-manage/actions/{a1}/daily-updates",
        json={
            "progress_percent": 30,
            "risk_blocker": "风险甲",
            "is_blocking": True,
            "progress_note": "本日进展说明已填写完毕",
        },
        headers=eng_headers,
    )
    client.post(
        "/api/test-manage/actions",
        json={"task_id": t2["id"], "title": "A2", "subtask_name": DEFAULT_SUBTASK_NAME, "publish": True},
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


# ── Task 需求属性扩展字段（SR编号/子类/优先级/验证等） ────────


def test_task_ext_fields_create_and_update(client, mgr_headers):
    """全字段创建 → 响应回显；更新单字段 → 生效。"""
    users = _users(client, mgr_headers)
    pid, did = _seed_project_domain(client, mgr_headers, "P-ext-fields")
    lead = users["eng_test"]["id"]
    verifier = users["eng_other"]["id"]

    r = client.post(
        "/api/test-manage/tasks",
        json={
            "project_id": pid,
            "domain_id": did,
            "title": "SR-TPT-X 智能问数",
            "requirement": "问数接入预测数据",
            "sr_code": "SR-TPT-00099",
            "ir_codes": "IR-TPT-00001，IR-TPT-00004",
            "module": "数据中心",
            "req_type": "功能",
            "priority": "高",
            "change_flag": "原始",
            "acceptance_criteria": "验收通过标准A",
            "verifier_id": verifier,
            "verify_result": "通过",
            "remark": "来自Excel导入",
            "lead_id": lead,
            "publish": True,
        },
        headers=mgr_headers,
    )
    assert r.status_code == 201, r.text
    t = r.json()
    assert t["sr_code"] == "SR-TPT-00099"
    assert t["ir_codes"] == "IR-TPT-00001，IR-TPT-00004"
    assert t["module"] == "数据中心"
    assert t["req_type"] == "功能"
    assert t["priority"] == "高"
    assert t["change_flag"] == "原始"
    assert t["acceptance_criteria"] == "验收通过标准A"
    assert t["verifier_id"] == verifier
    assert t["verify_result"] == "通过"
    assert t["remark"] == "来自Excel导入"

    # 更新单字段
    r = client.patch(
        f"/api/test-manage/tasks/{t['id']}",
        json={"priority": "中", "verify_result": "不通过"},
        headers=mgr_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["priority"] == "中"
    assert r.json()["verify_result"] == "不通过"
    # 未更新字段保持不变
    assert r.json()["sr_code"] == "SR-TPT-00099"


def test_task_module_required(client, mgr_headers):
    """module 必填：缺失 → 422。"""
    users = _users(client, mgr_headers)
    pid, did = _seed_project_domain(client, mgr_headers, "P-module-req")
    r = client.post(
        "/api/test-manage/tasks",
        json={
            "project_id": pid,
            "domain_id": did,
            "title": "无子类任务",
            "requirement": "缺 module 应被拒绝",
            "lead_id": users["eng_test"]["id"],
            "publish": False,
        },
        headers=mgr_headers,
    )
    assert r.status_code == 422, r.text


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
            "subtask_name": DEFAULT_SUBTASK_NAME,
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
            "subtask_name": DEFAULT_SUBTASK_NAME,
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
        json={"task_id": task["id"], "title": "未发布", "subtask_name": DEFAULT_SUBTASK_NAME, "publish": False},
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
        json={"task_id": task["id"], "title": "pct", "subtask_name": DEFAULT_SUBTASK_NAME, "publish": True},
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
            "subtask_name": DEFAULT_SUBTASK_NAME,
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


# ── 子需求移动（跨 Task，Action 随迁） ────────────────────────


def _subtasks_of(client, headers, task_id):
    r = client.get(f"/api/test-manage/tasks/{task_id}", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["subtasks"]


def _move_subtask(client, headers, task_id, sid, target_task_id):
    return client.post(
        f"/api/test-manage/tasks/{task_id}/subtasks/{sid}/move",
        json={"target_task_id": target_task_id},
        headers=headers,
    )


def test_subtask_move_migrates_actions(client, mgr_headers):
    """移动成功：源侧软删、目标侧新增、关联 Action 全部随迁。"""
    users = _users(client, mgr_headers)
    pid, did = _seed_project_domain(client, mgr_headers, "P-move")
    src = _seed_task(client, mgr_headers, pid, did, users["eng_test"]["id"], title="Move-Src")
    dst = _seed_task(client, mgr_headers, pid, did, users["eng_test"]["id"], title="Move-Dst")
    _seed_subtask(client, mgr_headers, src["id"], "待移动子需求", "内容A")
    r = client.post(
        "/api/test-manage/actions",
        json={
            "task_id": src["id"],
            "title": "Move-Action",
            "subtask_name": "待移动子需求",
            "owner_id": users["eng_test"]["id"],
            "publish": True,
        },
        headers=mgr_headers,
    )
    assert r.status_code == 201, r.text
    action_id = r.json()["id"]

    rows = _subtasks_of(client, mgr_headers, src["id"])
    sid = next(x["sid"] for x in rows if x["name"] == "待移动子需求")
    r = _move_subtask(client, mgr_headers, src["id"], sid, dst["id"])
    assert r.status_code == 200, r.text

    src_names = [x["name"] for x in _subtasks_of(client, mgr_headers, src["id"])]
    assert "待移动子需求" not in src_names
    assert DEFAULT_SUBTASK_NAME in src_names
    dst_names = [x["name"] for x in _subtasks_of(client, mgr_headers, dst["id"])]
    assert "待移动子需求" in dst_names
    # Action 随迁到目标 Task
    r = client.get(f"/api/test-manage/actions/{action_id}", headers=mgr_headers)
    assert r.status_code == 200, r.text
    assert r.json()["task_id"] == dst["id"]


def test_subtask_move_rejections(client, mgr_headers, eng2_headers):
    """移动校验：目标为自身 / 跨项目 / 目标重名 → 400；所有角色可创建并移动子需求。"""
    users = _users(client, mgr_headers)
    pid, did = _seed_project_domain(client, mgr_headers, "P-move-bad")
    src = _seed_task(client, mgr_headers, pid, did, users["eng_test"]["id"], title="MoveBad-Src")
    dst = _seed_task(client, mgr_headers, pid, did, users["eng_test"]["id"], title="MoveBad-Dst")
    sid = _subtasks_of(client, mgr_headers, src["id"])[0]["sid"]

    # 目标为自身
    assert _move_subtask(client, mgr_headers, src["id"], sid, src["id"]).status_code == 400

    # 跨项目
    pid2, did2 = _seed_project_domain(client, mgr_headers, "P-move-bad2")
    other = _seed_task(client, mgr_headers, pid2, did2, users["eng_test"]["id"], title="MoveBad-Other")
    assert _move_subtask(client, mgr_headers, src["id"], sid, other["id"]).status_code == 400

    # 目标重名（dst 已有同名默认子需求）
    assert _move_subtask(client, mgr_headers, src["id"], sid, dst["id"]).status_code == 400

    # 权限已放开：无关工程师也可创建并移动子需求（唯一命名避开重名校验）
    _seed_subtask(client, eng2_headers, src["id"], "Eng2可移动子需求", "内容")
    sid2 = next(
        x["sid"]
        for x in _subtasks_of(client, mgr_headers, src["id"])
        if x["name"] == "Eng2可移动子需求"
    )
    r = _move_subtask(client, eng2_headers, src["id"], sid2, dst["id"])
    assert r.status_code == 200, r.text
    assert "Eng2可移动子需求" in [
        x["name"] for x in _subtasks_of(client, mgr_headers, dst["id"])
    ]
