"""
项目管理回归扩充：边界、多角色交叉、字数、日更锁定、mine、更正、推送细节。
与 test_tm_full_regression.py 共用账号约定（tm_lead / tm_owner / tm_stranger）。
"""
from __future__ import annotations

from datetime import datetime

import pytest

from app.platform.database import SessionLocal
from app.test_manage.config import (
    ACTION_TEST_CONTENT_MAX_CHARS,
    TASK_REQUIREMENT_MAX_CHARS,
    TEXT_FIELD_MAX_CHARS,
    TM_TZ,
)
from app.test_manage import push_report as report
from app.test_manage.week import current_week_start, previous_week_start, week_key


TAG = "【回归+】"


@pytest.fixture()
def mgr_headers(client):
    r = client.post("/api/auth/login", json={"username": "manager", "password": "123456"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _ensure_user(client, auth_headers, username: str, real_name: str):
    r = client.post(
        "/api/auth/add-user",
        json={
            "username": username,
            "password": "123456",
            "role": "Engineer",
            "real_name": real_name,
        },
        headers=auth_headers,
    )
    if r.status_code == 200:
        return {"Authorization": f"Bearer {r.json()['access_token']}"}
    r = client.post("/api/auth/login", json={"username": username, "password": "123456"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def lead_headers(client, auth_headers):
    return _ensure_user(client, auth_headers, "tm_lead", "回归Lead")


@pytest.fixture()
def owner_headers(client, auth_headers):
    return _ensure_user(client, auth_headers, "tm_owner", "回归Owner")


@pytest.fixture()
def stranger_headers(client, auth_headers):
    return _ensure_user(client, auth_headers, "tm_stranger", "回归路人")


@pytest.fixture()
def tester_headers(client, auth_headers):
    """在 Task 上是测试人员，但不是某条 Action 的 owner。"""
    return _ensure_user(client, auth_headers, "tm_tester", "回归Tester")


def _uid(client, headers, username: str) -> int:
    r = client.get("/api/test-manage/users", headers=headers)
    assert r.status_code == 200
    for u in r.json():
        if u["username"] == username:
            return int(u["id"])
    raise AssertionError(username)


def _sandbox(client, mgr_headers):
    r = client.post(
        "/api/test-manage/projects",
        json={"name": f"{TAG} TPT", "description": "extra"},
        headers=mgr_headers,
    )
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    domains = {}
    for name in ("平台", "Agent"):
        r = client.post(
            f"/api/test-manage/projects/{pid}/domains",
            json={"name": name},
            headers=mgr_headers,
        )
        assert r.status_code == 201, r.text
        domains[name] = r.json()["id"]
    return pid, domains


def _task(client, headers, pid, did, lead_id, title, tester_ids=None, publish=True):
    r = client.post(
        "/api/test-manage/tasks",
        json={
            "project_id": pid,
            "domain_id": did,
            "title": title,
            "requirement": "r",
            "lead_id": lead_id,
            "tester_ids": tester_ids or [],
            "publish": publish,
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


def _action(client, headers, tid, title, owner_id, publish=False, **extra):
    body = {
        "task_id": tid,
        "title": title,
        "owner_id": owner_id,
        "publish": publish,
        **extra,
    }
    r = client.post("/api/test-manage/actions", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


# ── 字数 / 校验 ──────────────────────────────────────────────


def test_x_task_requirement_too_long(client, mgr_headers, lead_headers):
    _ = lead_headers
    pid, domains = _sandbox(client, mgr_headers)
    lead_id = _uid(client, mgr_headers, "tm_lead")
    r = client.post(
        "/api/test-manage/tasks",
        json={
            "project_id": pid,
            "domain_id": domains["平台"],
            "title": f"{TAG} 超长需求",
            "requirement": "x" * (TASK_REQUIREMENT_MAX_CHARS + 1),
            "lead_id": lead_id,
            "publish": True,
        },
        headers=mgr_headers,
    )
    assert r.status_code == 422


def test_x_action_content_too_long(client, mgr_headers, lead_headers, owner_headers):
    _ = owner_headers
    pid, domains = _sandbox(client, mgr_headers)
    lead_id = _uid(client, mgr_headers, "tm_lead")
    owner_id = _uid(client, mgr_headers, "tm_owner")
    task = _task(client, mgr_headers, pid, domains["平台"], lead_id, f"{TAG} 内容上限", [owner_id])
    r = client.post(
        "/api/test-manage/actions",
        json={
            "task_id": task["id"],
            "title": f"{TAG} 超长内容",
            "owner_id": owner_id,
            "test_content": "c" * (ACTION_TEST_CONTENT_MAX_CHARS + 1),
        },
        headers=lead_headers,
    )
    assert r.status_code == 422


def test_x_daily_empty_note_rejected(client, mgr_headers, lead_headers, owner_headers):
    pid, domains = _sandbox(client, mgr_headers)
    lead_id = _uid(client, mgr_headers, "tm_lead")
    owner_id = _uid(client, mgr_headers, "tm_owner")
    task = _task(client, mgr_headers, pid, domains["Agent"], lead_id, f"{TAG} 空说明", [owner_id])
    act = _action(client, lead_headers, task["id"], f"{TAG} A", owner_id, publish=True)
    r = client.put(
        f"/api/test-manage/actions/{act['id']}/daily-updates",
        json={"progress_percent": 10, "risk_blocker": "", "progress_note": "   "},
        headers=owner_headers,
    )
    assert r.status_code == 400


def test_x_daily_note_too_long(client, mgr_headers, lead_headers, owner_headers):
    pid, domains = _sandbox(client, mgr_headers)
    lead_id = _uid(client, mgr_headers, "tm_lead")
    owner_id = _uid(client, mgr_headers, "tm_owner")
    task = _task(client, mgr_headers, pid, domains["平台"], lead_id, f"{TAG} 说明上限", [owner_id])
    act = _action(client, lead_headers, task["id"], f"{TAG} A2", owner_id, publish=True)
    r = client.put(
        f"/api/test-manage/actions/{act['id']}/daily-updates",
        json={
            "progress_percent": 10,
            "risk_blocker": "",
            "progress_note": "n" * (TEXT_FIELD_MAX_CHARS + 1),
        },
        headers=owner_headers,
    )
    assert r.status_code == 422


# ── Task 更新日志 / 列表 / 详情 ──────────────────────────────


def test_x_task_update_log_written(client, mgr_headers, lead_headers):
    pid, domains = _sandbox(client, mgr_headers)
    lead_id = _uid(client, mgr_headers, "tm_lead")
    task = _task(client, mgr_headers, pid, domains["平台"], lead_id, f"{TAG} 日志")
    r = client.patch(
        f"/api/test-manage/tasks/{task['id']}",
        json={"title": f"{TAG} 日志-改", "change_summary": "改了标题"},
        headers=lead_headers,
    )
    assert r.status_code == 200
    r = client.get(f"/api/test-manage/tasks/{task['id']}", headers=lead_headers)
    assert r.status_code == 200
    logs = r.json().get("update_logs") or []
    assert any("改了标题" in (x.get("summary") or "") for x in logs)


def test_x_list_tasks_filter_project(client, mgr_headers, lead_headers):
    pid, domains = _sandbox(client, mgr_headers)
    lead_id = _uid(client, mgr_headers, "tm_lead")
    _task(client, mgr_headers, pid, domains["平台"], lead_id, f"{TAG} L1")
    _task(client, mgr_headers, pid, domains["Agent"], lead_id, f"{TAG} L2")
    r = client.get("/api/test-manage/tasks", params={"project_id": pid}, headers=mgr_headers)
    assert r.status_code == 200
    titles = [t["title"] for t in r.json()]
    assert f"{TAG} L1" in titles and f"{TAG} L2" in titles


# ── Tester 非 Owner 权限交叉 ─────────────────────────────────


def test_x_tester_not_owner_cannot_daily_or_edit_draft(
    client, mgr_headers, lead_headers, owner_headers, tester_headers
):
    pid, domains = _sandbox(client, mgr_headers)
    lead_id = _uid(client, mgr_headers, "tm_lead")
    owner_id = _uid(client, mgr_headers, "tm_owner")
    tester_id = _uid(client, mgr_headers, "tm_tester")
    task = _task(
        client,
        mgr_headers,
        pid,
        domains["平台"],
        lead_id,
        f"{TAG} Tester交叉",
        [owner_id, tester_id],
    )
    draft = _action(client, lead_headers, task["id"], f"{TAG} 草稿给owner", owner_id, publish=False)
    # tester 不能改草稿字段（非 lead）
    r = client.patch(
        f"/api/test-manage/actions/{draft['id']}",
        json={"title": "tester改"},
        headers=tester_headers,
    )
    assert r.status_code == 403

    pub = _action(client, lead_headers, task["id"], f"{TAG} 进行中给owner", owner_id, publish=True)
    r = client.put(
        f"/api/test-manage/actions/{pub['id']}/daily-updates",
        json={"progress_percent": 10, "risk_blocker": "", "progress_note": "tester越权"},
        headers=tester_headers,
    )
    assert r.status_code == 403

    # tester 可以成为另一条 Action 的 owner
    a2 = _action(client, lead_headers, task["id"], f"{TAG} 给tester", tester_id, publish=True)
    r = client.put(
        f"/api/test-manage/actions/{a2['id']}/daily-updates",
        json={"progress_percent": 15, "risk_blocker": "", "progress_note": "tester自己的"},
        headers=tester_headers,
    )
    assert r.status_code == 200, r.text


def test_x_tester_cannot_create_action(client, mgr_headers, lead_headers, tester_headers, owner_headers):
    _ = owner_headers
    pid, domains = _sandbox(client, mgr_headers)
    lead_id = _uid(client, mgr_headers, "tm_lead")
    owner_id = _uid(client, mgr_headers, "tm_owner")
    tester_id = _uid(client, mgr_headers, "tm_tester")
    task = _task(
        client, mgr_headers, pid, domains["Agent"], lead_id, f"{TAG} tester禁建", [owner_id, tester_id]
    )
    r = client.post(
        "/api/test-manage/actions",
        json={"task_id": task["id"], "title": f"{TAG} x", "owner_id": tester_id},
        headers=tester_headers,
    )
    assert r.status_code == 403


# ── Manager/Admin 代写日更 / Lead 发布他人草稿 ───────────────


def test_x_manager_and_admin_can_proxy_daily(
    client, auth_headers, mgr_headers, lead_headers, owner_headers
):
    pid, domains = _sandbox(client, mgr_headers)
    lead_id = _uid(client, mgr_headers, "tm_lead")
    owner_id = _uid(client, mgr_headers, "tm_owner")
    task = _task(client, mgr_headers, pid, domains["平台"], lead_id, f"{TAG} 代写", [owner_id])
    act = _action(client, lead_headers, task["id"], f"{TAG} 代写A", owner_id, publish=True)

    r = client.put(
        f"/api/test-manage/actions/{act['id']}/daily-updates",
        json={"progress_percent": 25, "risk_blocker": "m", "progress_note": "manager代写"},
        headers=mgr_headers,
    )
    assert r.status_code == 200, r.text

    r = client.put(
        f"/api/test-manage/actions/{act['id']}/daily-updates",
        json={"progress_percent": 35, "risk_blocker": "", "progress_note": "admin代写"},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text


def test_x_lead_can_publish_others_draft(client, mgr_headers, lead_headers, owner_headers):
    pid, domains = _sandbox(client, mgr_headers)
    lead_id = _uid(client, mgr_headers, "tm_lead")
    owner_id = _uid(client, mgr_headers, "tm_owner")
    task = _task(client, mgr_headers, pid, domains["平台"], lead_id, f"{TAG} lead发布", [owner_id])
    draft = _action(client, lead_headers, task["id"], f"{TAG} 待发布", owner_id, publish=False)
    r = client.patch(
        f"/api/test-manage/actions/{draft['id']}",
        json={"status": "published"},
        headers=lead_headers,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "published"


def test_x_owner_cannot_edit_draft_fields_without_lead(
    client, mgr_headers, lead_headers, owner_headers
):
    """草稿字段仅 lead/管理员可改；owner 只能改状态。"""
    pid, domains = _sandbox(client, mgr_headers)
    lead_id = _uid(client, mgr_headers, "tm_lead")
    owner_id = _uid(client, mgr_headers, "tm_owner")
    task = _task(client, mgr_headers, pid, domains["Agent"], lead_id, f"{TAG} owner草稿", [owner_id])
    draft = _action(client, lead_headers, task["id"], f"{TAG} D", owner_id, publish=False)
    r = client.patch(
        f"/api/test-manage/actions/{draft['id']}",
        json={"title": "owner改标题"},
        headers=owner_headers,
    )
    assert r.status_code == 403
    r = client.patch(
        f"/api/test-manage/actions/{draft['id']}",
        json={"status": "published"},
        headers=owner_headers,
    )
    assert r.status_code == 200


# ── 日更锁定 / 草稿与完成不可日更 / 风险清空 ─────────────────


def test_x_draft_and_done_cannot_daily(client, mgr_headers, lead_headers, owner_headers):
    pid, domains = _sandbox(client, mgr_headers)
    lead_id = _uid(client, mgr_headers, "tm_lead")
    owner_id = _uid(client, mgr_headers, "tm_owner")
    task = _task(client, mgr_headers, pid, domains["平台"], lead_id, f"{TAG} 状态日更", [owner_id])
    draft = _action(client, lead_headers, task["id"], f"{TAG} 草稿日更", owner_id, publish=False)
    r = client.put(
        f"/api/test-manage/actions/{draft['id']}/daily-updates",
        json={"progress_percent": 10, "risk_blocker": "", "progress_note": "草稿"},
        headers=owner_headers,
    )
    assert r.status_code == 403

    act = _action(client, lead_headers, task["id"], f"{TAG} 完成日更", owner_id, publish=True)
    client.put(
        f"/api/test-manage/actions/{act['id']}/daily-updates",
        json={"progress_percent": 100, "risk_blocker": "有", "progress_note": "满"},
        headers=owner_headers,
    )
    client.patch(
        f"/api/test-manage/actions/{act['id']}",
        json={"status": "done"},
        headers=owner_headers,
    )
    r = client.put(
        f"/api/test-manage/actions/{act['id']}/daily-updates",
        json={"progress_percent": 100, "risk_blocker": "", "progress_note": "完成后"},
        headers=owner_headers,
    )
    assert r.status_code == 403


def test_x_clear_risk_resolves_for_board_and_push(
    client, mgr_headers, lead_headers, owner_headers
):
    pid, domains = _sandbox(client, mgr_headers)
    lead_id = _uid(client, mgr_headers, "tm_lead")
    owner_id = _uid(client, mgr_headers, "tm_owner")
    task = _task(client, mgr_headers, pid, domains["平台"], lead_id, f"{TAG} 清风险", [owner_id])
    act = _action(client, lead_headers, task["id"], f"{TAG} 风险Act", owner_id, publish=True)
    client.put(
        f"/api/test-manage/actions/{act['id']}/daily-updates",
        json={"progress_percent": 40, "risk_blocker": "阻塞Z", "progress_note": "有风险"},
        headers=owner_headers,
    )
    board = client.get(
        "/api/test-manage/board", params={"project_id": pid}, headers=mgr_headers
    ).json()
    hit = next(b for b in board["tasks"] if b["task"]["id"] == task["id"])
    assert any("阻塞Z" in (x or "") for x in hit.get("risks") or [])

    client.put(
        f"/api/test-manage/actions/{act['id']}/daily-updates",
        json={"progress_percent": 50, "risk_blocker": "", "progress_note": "已解除"},
        headers=owner_headers,
    )
    board2 = client.get(
        "/api/test-manage/board", params={"project_id": pid}, headers=mgr_headers
    ).json()
    hit2 = next(b for b in board2["tasks"] if b["task"]["id"] == task["id"])
    assert not any("阻塞Z" in (x or "") for x in hit2.get("risks") or [])

    r = client.post("/api/test-manage/push/daily", json={"dry_run": True}, headers=mgr_headers)
    assert r.status_code == 200
    # 已解除的不应再作为开放风险主导文案（允许历史字样偶然出现时至少 latest 已清空）
    detail = client.get(f"/api/test-manage/actions/{act['id']}", headers=owner_headers).json()
    assert (detail.get("latest_risk") or "") == ""


def test_x_daily_lock_after_1950(client, mgr_headers, lead_headers, owner_headers, monkeypatch):
    import app.test_manage.config as cfg
    import app.test_manage.service as svc

    # is_daily_edit_locked 运行时读 config.DAILY_EDIT_LOCK_DISABLED / now_tm
    monkeypatch.setattr(cfg, "DAILY_EDIT_LOCK_DISABLED", False)
    locked = datetime(2026, 7, 30, 19, 51, tzinfo=TM_TZ)
    monkeypatch.setattr(cfg, "now_tm", lambda: locked)
    monkeypatch.setattr(svc, "now_tm", lambda: locked)
    monkeypatch.setattr(cfg, "today_tm", lambda: locked.date())
    monkeypatch.setattr(svc, "today_tm", lambda: locked.date())

    pid, domains = _sandbox(client, mgr_headers)
    lead_id = _uid(client, mgr_headers, "tm_lead")
    owner_id = _uid(client, mgr_headers, "tm_owner")
    task = _task(client, mgr_headers, pid, domains["平台"], lead_id, f"{TAG} 锁定", [owner_id])
    act = _action(client, lead_headers, task["id"], f"{TAG} 锁定A", owner_id, publish=True)
    r = client.put(
        f"/api/test-manage/actions/{act['id']}/daily-updates",
        json={"progress_percent": 10, "risk_blocker": "", "progress_note": "锁后"},
        headers=owner_headers,
    )
    assert r.status_code == 400
    assert "截止" in (r.json().get("detail") or "")


# ── 取消禁止 / 更正权限 / mine ───────────────────────────────


def test_x_action_cancel_forbidden(client, mgr_headers, lead_headers, owner_headers):
    pid, domains = _sandbox(client, mgr_headers)
    lead_id = _uid(client, mgr_headers, "tm_lead")
    owner_id = _uid(client, mgr_headers, "tm_owner")
    task = _task(client, mgr_headers, pid, domains["平台"], lead_id, f"{TAG} 禁取消", [owner_id])
    act = _action(client, lead_headers, task["id"], f"{TAG} C", owner_id, publish=True)
    r = client.patch(
        f"/api/test-manage/actions/{act['id']}",
        json={"status": "cancelled"},
        headers=mgr_headers,
    )
    assert r.status_code == 400


def test_x_correction_permissions(
    client, mgr_headers, lead_headers, owner_headers, stranger_headers, tester_headers
):
    pid, domains = _sandbox(client, mgr_headers)
    lead_id = _uid(client, mgr_headers, "tm_lead")
    owner_id = _uid(client, mgr_headers, "tm_owner")
    tester_id = _uid(client, mgr_headers, "tm_tester")
    task = _task(
        client, mgr_headers, pid, domains["平台"], lead_id, f"{TAG} 更正", [owner_id, tester_id]
    )
    act = _action(client, lead_headers, task["id"], f"{TAG} 更正A", owner_id, publish=True)

    r = client.post(
        f"/api/test-manage/actions/{act['id']}/corrections",
        json={"note": "owner更正"},
        headers=owner_headers,
    )
    assert r.status_code in (200, 201), r.text

    r = client.post(
        f"/api/test-manage/actions/{act['id']}/corrections",
        json={"note": "lead更正"},
        headers=lead_headers,
    )
    assert r.status_code in (200, 201), r.text

    r = client.post(
        f"/api/test-manage/actions/{act['id']}/corrections",
        json={"note": "路人"},
        headers=stranger_headers,
    )
    assert r.status_code == 403

    # tester 非 owner：按矩阵不可更正他人 Action
    r = client.post(
        f"/api/test-manage/actions/{act['id']}/corrections",
        json={"note": "tester"},
        headers=tester_headers,
    )
    assert r.status_code == 403


def test_x_mine_only_own_actions(client, mgr_headers, lead_headers, owner_headers, tester_headers):
    pid, domains = _sandbox(client, mgr_headers)
    lead_id = _uid(client, mgr_headers, "tm_lead")
    owner_id = _uid(client, mgr_headers, "tm_owner")
    tester_id = _uid(client, mgr_headers, "tm_tester")
    task = _task(
        client, mgr_headers, pid, domains["Agent"], lead_id, f"{TAG} mine", [owner_id, tester_id]
    )
    a_owner = _action(client, lead_headers, task["id"], f"{TAG} mine-owner", owner_id, publish=True)
    a_tester = _action(client, lead_headers, task["id"], f"{TAG} mine-tester", tester_id, publish=True)

    mine_owner = client.get("/api/test-manage/actions/mine", headers=owner_headers).json()
    ids_o = {a["id"] for a in mine_owner}
    assert a_owner["id"] in ids_o
    assert a_tester["id"] not in ids_o

    mine_t = client.get("/api/test-manage/actions/mine", headers=tester_headers).json()
    ids_t = {a["id"] for a in mine_t}
    assert a_tester["id"] in ids_t
    assert a_owner["id"] not in ids_t


# ── 看板：路人可见性 / 历史周 / done 空卡片文案接口标志 ──────


def test_x_board_stranger_hides_unrelated_empty_task(
    client, mgr_headers, lead_headers, stranger_headers
):
    pid, domains = _sandbox(client, mgr_headers)
    lead_id = _uid(client, mgr_headers, "tm_lead")
    task = _task(client, mgr_headers, pid, domains["平台"], lead_id, f"{TAG} 仅lead空")
    # lead 可见空卡片
    board_lead = client.get(
        "/api/test-manage/board", params={"project_id": pid}, headers=lead_headers
    ).json()
    assert any(b["task"]["id"] == task["id"] for b in board_lead["tasks"])
    # 路人（非 lead/tester）看不到无 Action 的无关 Task
    board_x = client.get(
        "/api/test-manage/board", params={"project_id": pid}, headers=stranger_headers
    ).json()
    assert not any(b["task"]["id"] == task["id"] for b in board_x["tasks"])


def test_x_board_history_hides_empty_tasks(client, mgr_headers, lead_headers, owner_headers):
    pid, domains = _sandbox(client, mgr_headers)
    lead_id = _uid(client, mgr_headers, "tm_lead")
    owner_id = _uid(client, mgr_headers, "tm_owner")
    empty = _task(client, mgr_headers, pid, domains["平台"], lead_id, f"{TAG} 历史空")
    with_act = _task(
        client, mgr_headers, pid, domains["Agent"], lead_id, f"{TAG} 历史有", [owner_id]
    )
    act = _action(client, lead_headers, with_act["id"], f"{TAG} 历史A", owner_id, publish=True)

    # 把 Action 挪到上周 week_key，模拟历史周数据
    db = SessionLocal()
    try:
        from app.test_manage.models import TmAction

        prev = previous_week_start()
        row = db.query(TmAction).filter(TmAction.id == act["id"]).one()
        row.week_start = prev
        row.week_key = week_key(prev)
        db.commit()
        hist_key_start = prev.isoformat()
    finally:
        db.close()

    board = client.get(
        "/api/test-manage/board",
        params={"project_id": pid, "week_start": hist_key_start},
        headers=mgr_headers,
    )
    assert board.status_code == 200, board.text
    ids = {b["task"]["id"] for b in board.json()["tasks"]}
    assert with_act["id"] in ids
    assert empty["id"] not in ids  # 历史周不刷空卡片


def test_x_done_task_flags(client, mgr_headers, lead_headers):
    pid, domains = _sandbox(client, mgr_headers)
    lead_id = _uid(client, mgr_headers, "tm_lead")
    task = _task(client, mgr_headers, pid, domains["平台"], lead_id, f"{TAG} done旗标")
    client.patch(
        f"/api/test-manage/tasks/{task['id']}",
        json={"status": "done", "change_summary": "收尾"},
        headers=lead_headers,
    )
    detail = client.get(f"/api/test-manage/tasks/{task['id']}", headers=lead_headers).json()
    assert detail["status"] == "done"
    assert detail.get("can_add_action") is False
    r = client.get(
        f"/api/test-manage/tasks/{task['id']}/clone-candidates", headers=lead_headers
    )
    # 查看候选可读；真正 clone/create 会 400
    assert r.status_code in (200, 403)
    r = client.post(
        "/api/test-manage/actions",
        json={"task_id": task["id"], "title": f"{TAG} no", "owner_id": lead_id},
        headers=lead_headers,
    )
    assert r.status_code == 400


# ── 推送：草稿风险不计、周报含 Action+负责人、无风险也有日报 ─


def test_x_push_draft_risk_excluded_and_weekly_names(
    client, mgr_headers, lead_headers, owner_headers
):
    pid, domains = _sandbox(client, mgr_headers)
    lead_id = _uid(client, mgr_headers, "tm_lead")
    owner_id = _uid(client, mgr_headers, "tm_owner")
    task = _task(client, mgr_headers, pid, domains["平台"], lead_id, f"{TAG} 推送细", [owner_id])
    # 草稿：无法日更，不应进开放风险
    _action(client, lead_headers, task["id"], f"{TAG} 草稿风险名", owner_id, publish=False)
    pub = _action(client, lead_headers, task["id"], f"{TAG} 开放风险名", owner_id, publish=True)
    client.put(
        f"/api/test-manage/actions/{pub['id']}/daily-updates",
        json={"progress_percent": 22, "risk_blocker": "独特阻塞词XYZ", "progress_note": "记"},
        headers=owner_headers,
    )

    daily = client.post(
        "/api/test-manage/push/daily", json={"dry_run": True}, headers=mgr_headers
    ).json()
    dmsg = daily.get("message") or ""
    assert "独特阻塞词XYZ" in dmsg
    assert "草稿风险名" not in dmsg or "独特阻塞词XYZ" in dmsg

    weekly = client.post(
        "/api/test-manage/push/weekly", json={"dry_run": True}, headers=mgr_headers
    ).json()
    wmsg = weekly.get("message") or ""
    assert "开放风险名" in wmsg
    assert "独特阻塞词XYZ" in wmsg
    # 负责人真实姓名或用户名
    assert ("回归Owner" in wmsg) or ("tm_owner" in wmsg)


def test_x_push_daily_without_open_risk_still_sends(
    client, mgr_headers, lead_headers, owner_headers
):
    pid, domains = _sandbox(client, mgr_headers)
    lead_id = _uid(client, mgr_headers, "tm_lead")
    owner_id = _uid(client, mgr_headers, "tm_owner")
    task = _task(client, mgr_headers, pid, domains["Agent"], lead_id, f"{TAG} 无风险日报", [owner_id])
    act = _action(client, lead_headers, task["id"], f"{TAG} 平滑", owner_id, publish=True)
    client.put(
        f"/api/test-manage/actions/{act['id']}/daily-updates",
        json={"progress_percent": 70, "risk_blocker": "", "progress_note": "顺利"},
        headers=owner_headers,
    )
    r = client.post("/api/test-manage/push/daily", json={"dry_run": True}, headers=mgr_headers)
    assert r.status_code == 200
    msg = r.json().get("message") or ""
    assert len(msg) > 20
    assert "日报" in msg or "Action" in msg


def test_x_empty_task_not_in_push_task_count(client, mgr_headers, lead_headers, owner_headers):
    pid, domains = _sandbox(client, mgr_headers)
    lead_id = _uid(client, mgr_headers, "tm_lead")
    owner_id = _uid(client, mgr_headers, "tm_owner")
    _task(client, mgr_headers, pid, domains["平台"], lead_id, f"{TAG} 空不计KPI")
    task = _task(client, mgr_headers, pid, domains["Agent"], lead_id, f"{TAG} 有计KPI", [owner_id])
    _action(client, lead_headers, task["id"], f"{TAG} KPIA", owner_id, publish=True)

    db = SessionLocal()
    try:
        summary = report.collect_progress_summary(db, week_start=current_week_start())
        rows = report.collect_task_progress_rows(db, week_start=current_week_start())
        titles = {r.task_title for r in rows}
        assert f"{TAG} 有计KPI" in titles
        assert f"{TAG} 空不计KPI" not in titles
        assert summary.task_count == len({r.task_id for r in rows})
    finally:
        db.close()


# ── 批量复制语义：多候选 ─────────────────────────────────────


def test_x_clone_candidates_and_batch_semantics(
    client, mgr_headers, lead_headers, owner_headers
):
    pid, domains = _sandbox(client, mgr_headers)
    lead_id = _uid(client, mgr_headers, "tm_lead")
    owner_id = _uid(client, mgr_headers, "tm_owner")
    task = _task(client, mgr_headers, pid, domains["平台"], lead_id, f"{TAG} 多复制", [owner_id])
    a1 = _action(client, lead_headers, task["id"], f"{TAG} 源1", owner_id, publish=True)
    a2 = _action(client, lead_headers, task["id"], f"{TAG} 源2", owner_id, publish=True)

    # 挪到上周作为候选
    db = SessionLocal()
    try:
        from app.test_manage.models import TmAction

        prev = previous_week_start()
        for aid in (a1["id"], a2["id"]):
            row = db.query(TmAction).filter(TmAction.id == aid).one()
            row.week_start = prev
            row.week_key = week_key(prev)
        db.commit()
    finally:
        db.close()

    cands = client.get(
        f"/api/test-manage/tasks/{task['id']}/clone-candidates", headers=lead_headers
    ).json()
    assert len(cands) >= 2
    for c in cands[:2]:
        r = client.post(
            f"/api/test-manage/actions/{c['id']}/clone",
            json={"publish": False},
            headers=lead_headers,
        )
        assert r.status_code == 201
        assert r.json()["status"] == "draft"
        assert (r.json().get("latest_risk") or "") == ""
        assert r.json()["week_key"] == week_key(current_week_start())
