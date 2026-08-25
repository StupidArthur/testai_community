"""
权限矩阵 / 边界 / 异常场景专项（补齐既有套件缺口）。

覆盖：发布后负责人锁定、占位账号、推送权限、风险已解决语义、非法状态、看板口径等。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from app.platform.database import SessionLocal
from app.test_manage.config import TM_TZ
from app.test_manage.models import TmAction, TmDailyUpdate
from app.test_manage.service import _latest_progress
from app.test_manage.week import current_week_start, previous_week_start, week_key


@pytest.fixture()
def mgr_headers(client):
    r = client.post("/api/auth/login", json={"username": "manager", "password": "123456"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def eng2_headers(client, auth_headers):
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


def _seed_pd(client, headers, name: str):
    r = client.post(
        "/api/test-manage/projects",
        json={"name": name, "description": "audit"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    r = client.post(
        f"/api/test-manage/projects/{pid}/domains",
        json={"name": "域A"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return pid, r.json()["id"]


def _seed_task(client, headers, pid, did, lead_id, tester_ids=None, publish=True):
    r = client.post(
        "/api/test-manage/tasks",
        json={
            "project_id": pid,
            "domain_id": did,
            "title": "T",
            "requirement": "r",
            "lead_id": lead_id,
            "tester_ids": tester_ids or [],
            "publish": publish,
            "req_stage": "testing",
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


# ── 风险已解决语义（文档：最新日更 risk 为空 = 已解决）──


def test_latest_progress_cleared_risk_is_resolved():
    """最新日更清空 risk_blocker 后，展示/推送不得再沿用旧风险。"""
    older = TmDailyUpdate(
        id="u1",
        action_id="a",
        user_id=1,
        report_date=date(2026, 7, 20),
        progress_percent=50,
        risk_blocker="旧阻塞",
        progress_note="",
        created_at=datetime(2026, 7, 20, 10, 0),
        updated_at=datetime(2026, 7, 20, 10, 0),
    )
    newer = TmDailyUpdate(
        id="u2",
        action_id="a",
        user_id=1,
        report_date=date(2026, 7, 21),
        progress_percent=80,
        risk_blocker="",  # 已解决
        progress_note="已修复",
        created_at=datetime(2026, 7, 21, 10, 0),
        updated_at=datetime(2026, 7, 21, 10, 0),
    )
    action = TmAction(id="a", daily_updates=[older, newer])
    progress, risk, _blocking = _latest_progress(action)
    assert progress == 80
    assert risk == "", f"期望已解决为空，实际仍为: {risk!r}"


# ── 占位账号 ──


def test_placeholder_user_cannot_login(client, auth_headers):
    from app.auth.models import User, UserRole
    from app.auth.service import hash_password
    from app.platform.database import SessionLocal

    with SessionLocal() as db:
        row = db.query(User).filter(User.username == "无").first()
        if not row:
            db.add(
                User(
                    username="无",
                    password_hash=hash_password("123456"),
                    role=UserRole.Engineer,
                    real_name="无",
                )
            )
            db.commit()

    r = client.post("/api/auth/login", json={"username": "无", "password": "123456"})
    assert r.status_code == 401
    assert "占位" in r.json()["detail"] or "不可登录" in r.json()["detail"]


def test_assignable_users_exclude_placeholder(client, auth_headers):
    from app.auth.models import User, UserRole
    from app.auth.service import hash_password
    from app.platform.database import SessionLocal

    with SessionLocal() as db:
        if not db.query(User).filter(User.username == "无").first():
            db.add(
                User(
                    username="无",
                    password_hash=hash_password("123456"),
                    role=UserRole.Engineer,
                    real_name="无",
                )
            )
            db.commit()

    r = client.get("/api/test-manage/users", headers=auth_headers)
    assert r.status_code == 200
    assert all(u["username"] != "无" for u in r.json())


# ── 发布后负责人锁定 ──


def test_published_owner_locked_even_for_admin(client, auth_headers, eng_headers, eng2_headers):
    """发布后本周负责人不可改（含 Admin）；草稿阶段仍可改。"""
    users = _users(client, auth_headers)
    client.get("/api/test-manage/week", headers=eng2_headers)
    users = _users(client, auth_headers)
    pid, did = _seed_pd(client, auth_headers, "P-owner-lock")
    task = _seed_task(
        client,
        auth_headers,
        pid,
        did,
        users["eng_test"]["id"],
        tester_ids=[users["eng_other"]["id"]],
    )
    r = client.post(
        "/api/test-manage/actions",
        json={
            "task_id": task["id"],
            "title": "草稿可改负责人",
            "owner_id": users["eng_test"]["id"],
            "publish": False,
        },
        headers=eng_headers,
    )
    assert r.status_code == 201, r.text
    aid = r.json()["id"]
    r = client.patch(
        f"/api/test-manage/actions/{aid}",
        json={"owner_id": users["eng_other"]["id"]},
        headers=eng_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["owner_id"] == users["eng_other"]["id"]

    r = client.patch(
        f"/api/test-manage/actions/{aid}",
        json={"status": "published"},
        headers=eng_headers,
    )
    assert r.status_code == 200, r.text

    r = client.patch(
        f"/api/test-manage/actions/{aid}",
        json={"owner_id": users["eng_test"]["id"]},
        headers=auth_headers,
    )
    assert r.status_code == 403
    assert "锁定" in r.json()["detail"]


# ── 推送权限 ──


def test_engineer_cannot_push(client, eng_headers):
    r = client.post(
        "/api/test-manage/push/daily",
        json={"dry_run": True},
        headers=eng_headers,
    )
    assert r.status_code == 403

    r = client.get("/api/test-manage/push/status", headers=eng_headers)
    assert r.status_code == 403


def test_manager_can_dry_run_push(client, mgr_headers):
    r = client.post(
        "/api/test-manage/push/daily",
        json={"dry_run": True},
        headers=mgr_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dry_run"] is True
    assert "sent" in body or "skipped" in body or body.get("kind") == "daily"


# ── Task lead 不能代写他人 Action 日更 ──


def test_task_lead_cannot_daily_others_action(client, auth_headers, eng_headers, eng2_headers):
    users = _users(client, auth_headers)
    client.get("/api/test-manage/week", headers=eng2_headers)
    users = _users(client, auth_headers)
    pid, did = _seed_pd(client, auth_headers, "P-lead-daily")
    # lead=eng_test, owner=eng_other
    task = _seed_task(
        client,
        auth_headers,
        pid,
        did,
        users["eng_test"]["id"],
        tester_ids=[users["eng_other"]["id"]],
    )
    r = client.post(
        "/api/test-manage/actions",
        json={
            "task_id": task["id"],
            "title": "他人负责",
            "owner_id": users["eng_other"]["id"],
            "publish": True,
        },
        headers=eng_headers,
    )
    assert r.status_code == 201, r.text
    aid = r.json()["id"]
    r = client.put(
        f"/api/test-manage/actions/{aid}/daily-updates",
        json={"progress_percent": 1, "risk_blocker": "", "progress_note": "本日进展说明已填写完毕"},
        headers=eng_headers,
    )
    assert r.status_code == 403


# ── 非法状态跳转（当前实现允许 —— 记为行为断言，便于产品决策）──


def test_action_owner_can_mark_done(client, auth_headers, eng_headers, eng2_headers):
    """Action 本周负责人可自行 published→done；无关人员不可。"""
    users = _users(client, auth_headers)
    client.get("/api/test-manage/week", headers=eng2_headers)
    users = _users(client, auth_headers)
    pid, did = _seed_pd(client, auth_headers, "P-owner-status")
    task = _seed_task(
        client,
        auth_headers,
        pid,
        did,
        users["eng_test"]["id"],
        tester_ids=[users["eng_other"]["id"]],
    )
    r = client.post(
        "/api/test-manage/actions",
        json={
            "task_id": task["id"],
            "title": "owner可完成",
            "owner_id": users["eng_other"]["id"],
            "publish": True,
        },
        headers=eng_headers,
    )
    assert r.status_code == 201, r.text
    aid = r.json()["id"]

    r = client.get(f"/api/test-manage/actions/{aid}", headers=eng2_headers)
    assert r.status_code == 200
    assert r.json()["can_change_status"] is True
    assert r.json()["can_mark_done"] is False  # 无日更进度=0，不可完成

    r = client.patch(
        f"/api/test-manage/actions/{aid}",
        json={"status": "done"},
        headers=eng2_headers,
    )
    assert r.status_code == 400
    assert "100%" in r.json()["detail"]

    r = client.put(
        f"/api/test-manage/actions/{aid}/daily-updates",
        json={"progress_percent": 100, "progress_note": "本日进展说明已填写完毕"},
        headers=eng2_headers,
    )
    assert r.status_code == 200, r.text
    r = client.get(f"/api/test-manage/actions/{aid}", headers=eng2_headers)
    assert r.json()["can_mark_done"] is True
    assert r.json()["progress_percent"] == 100

    r = client.patch(
        f"/api/test-manage/actions/{aid}",
        json={"status": "done"},
        headers=eng2_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "done"

    r = client.post(
        "/api/test-manage/actions",
        json={
            "task_id": task["id"],
            "title": "非owner不可",
            "owner_id": users["eng_test"]["id"],
            "publish": True,
        },
        headers=eng_headers,
    )
    aid2 = r.json()["id"]
    r = client.patch(
        f"/api/test-manage/actions/{aid2}",
        json={"status": "done"},
        headers=eng2_headers,
    )
    # eng_other 是 tester 但非 owner、非 lead → 403
    assert r.status_code == 403


def test_action_cannot_be_cancelled(client, auth_headers, eng_headers):
    """Action 不支持取消（草稿/进行中均拒绝）。"""
    users = _users(client, auth_headers)
    pid, did = _seed_pd(client, auth_headers, "P-no-cancel")
    task = _seed_task(client, auth_headers, pid, did, users["eng_test"]["id"])
    r = client.post(
        "/api/test-manage/actions",
        json={
            "task_id": task["id"],
            "title": "不可取消",
            "owner_id": users["eng_test"]["id"],
            "publish": True,
        },
        headers=eng_headers,
    )
    aid = r.json()["id"]
    r = client.patch(
        f"/api/test-manage/actions/{aid}",
        json={"status": "cancelled"},
        headers=auth_headers,
    )
    assert r.status_code == 400
    assert "不支持取消" in r.json()["detail"]

    r = client.post(
        "/api/test-manage/actions",
        json={
            "task_id": task["id"],
            "title": "草稿也不可取消",
            "owner_id": users["eng_test"]["id"],
            "publish": False,
        },
        headers=eng_headers,
    )
    aid_d = r.json()["id"]
    r = client.patch(
        f"/api/test-manage/actions/{aid_d}",
        json={"status": "cancelled"},
        headers=auth_headers,
    )
    assert r.status_code == 400
    assert "不支持取消" in r.json()["detail"]


def test_done_action_cannot_reopen_to_published(client, auth_headers, eng_headers):
    """已完成不可重开为进行中。"""
    users = _users(client, auth_headers)
    pid, did = _seed_pd(client, auth_headers, "P-done-lock")
    task = _seed_task(client, auth_headers, pid, did, users["eng_test"]["id"])
    r = client.post(
        "/api/test-manage/actions",
        json={
            "task_id": task["id"],
            "title": "完成后锁定",
            "owner_id": users["eng_test"]["id"],
            "publish": True,
        },
        headers=eng_headers,
    )
    aid = r.json()["id"]
    r = client.put(
        f"/api/test-manage/actions/{aid}/daily-updates",
        json={"progress_percent": 100, "progress_note": "本日进展说明已填写完毕"},
        headers=eng_headers,
    )
    assert r.status_code == 200, r.text
    r = client.patch(
        f"/api/test-manage/actions/{aid}",
        json={"status": "done"},
        headers=eng_headers,
    )
    assert r.status_code == 200, r.text
    r = client.patch(
        f"/api/test-manage/actions/{aid}",
        json={"status": "published"},
        headers=auth_headers,
    )
    assert r.status_code == 400
    assert "不可" in r.json()["detail"]


def test_cannot_mark_done_unless_progress_100(client, auth_headers, eng_headers):
    """进度未满 100% 不可 published→done；80% 拒绝，100% 通过。"""
    users = _users(client, auth_headers)
    pid, did = _seed_pd(client, auth_headers, "P-done-pct")
    task = _seed_task(client, auth_headers, pid, did, users["eng_test"]["id"])
    r = client.post(
        "/api/test-manage/actions",
        json={
            "task_id": task["id"],
            "title": "进度门槛",
            "owner_id": users["eng_test"]["id"],
            "publish": True,
        },
        headers=eng_headers,
    )
    aid = r.json()["id"]

    r = client.put(
        f"/api/test-manage/actions/{aid}/daily-updates",
        json={"progress_percent": 80, "progress_note": "本日进展说明已填写完毕"},
        headers=eng_headers,
    )
    assert r.status_code == 200
    r = client.get(f"/api/test-manage/actions/{aid}", headers=eng_headers)
    assert r.json()["progress_percent"] == 80
    assert r.json()["can_mark_done"] is False

    r = client.patch(
        f"/api/test-manage/actions/{aid}",
        json={"status": "done"},
        headers=eng_headers,
    )
    assert r.status_code == 400
    assert "100%" in r.json()["detail"]

    r = client.put(
        f"/api/test-manage/actions/{aid}/daily-updates",
        json={"progress_percent": 100, "progress_note": "本日进展说明已填写完毕"},
        headers=eng_headers,
    )
    assert r.status_code == 200
    r = client.get(f"/api/test-manage/actions/{aid}", headers=eng_headers)
    assert r.json()["can_mark_done"] is True
    r = client.patch(
        f"/api/test-manage/actions/{aid}",
        json={"status": "done"},
        headers=eng_headers,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "done"


# ── mine 不含非本周 / 历史 cancelled ──


def test_mine_excludes_previous_week_and_cancelled(client, auth_headers, eng_headers):
    users = _users(client, auth_headers)
    pid, did = _seed_pd(client, auth_headers, "P-mine-week")
    task = _seed_task(client, auth_headers, pid, did, users["eng_test"]["id"])
    r = client.post(
        "/api/test-manage/actions",
        json={
            "task_id": task["id"],
            "title": "本周我的",
            "owner_id": users["eng_test"]["id"],
            "publish": True,
        },
        headers=eng_headers,
    )
    aid_cur = r.json()["id"]

    # 直接插一条上周 Action + 一条历史 cancelled（产品已禁止新取消，用 DB 模拟存量）
    prev_ws = previous_week_start()
    with SessionLocal() as db:
        cur = db.query(TmAction).filter(TmAction.id == aid_cur).first()
        old = TmAction(
            task_id=cur.task_id,
            project_id=cur.project_id,
            domain_id=cur.domain_id,
            week_start=prev_ws,
            week_key=week_key(prev_ws),
            title="上周我的",
            owner_id=cur.owner_id,
            test_content="",
            environment="",
            status="published",
            created_by=cur.created_by,
            published_at=prev_ws,
            due_at=prev_ws + timedelta(days=7),
        )
        db.add(old)
        cxl = TmAction(
            task_id=cur.task_id,
            project_id=cur.project_id,
            domain_id=cur.domain_id,
            week_start=cur.week_start,
            week_key=cur.week_key,
            title="历史取消",
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
        old_id = old.id
        cxl_id = cxl.id

    r = client.get("/api/test-manage/actions/mine", headers=eng_headers)
    assert r.status_code == 200
    ids = {a["id"] for a in r.json()}
    assert aid_cur in ids
    assert old_id not in ids
    assert cxl_id not in ids


# ── 清空风险后看板/详情应已解决（端到端，期望失败则暴露 bug）──


def test_daily_is_blocking_roundtrip_on_board(client, auth_headers, eng_headers):
    """勾选是否阻塞后，看板 latest_is_blocking / risks 必须为真。"""
    users = _users(client, auth_headers)
    pid, did = _seed_pd(client, auth_headers, "P-is-blocking")
    task = _seed_task(client, auth_headers, pid, did, users["eng_test"]["id"])
    r = client.post(
        "/api/test-manage/actions",
        json={
            "task_id": task["id"],
            "title": "阻塞勾选",
            "owner_id": users["eng_test"]["id"],
            "publish": True,
        },
        headers=eng_headers,
    )
    aid = r.json()["id"]

    r = client.put(
        f"/api/test-manage/actions/{aid}/daily-updates",
        json={
            "progress_percent": 30,
            "risk_blocker": "环境不可用",
            "is_blocking": True,
            "progress_note": "本日进展说明已填写完毕",
        },
        headers=eng_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["is_blocking"] is True

    r = client.get(f"/api/test-manage/actions/{aid}", headers=eng_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["latest_risk"] == "环境不可用"
    assert body["latest_is_blocking"] is True

    board = client.get("/api/test-manage/board", headers=auth_headers)
    assert board.status_code == 200
    actions = [a for t in board.json()["tasks"] for a in t["actions"] if a["id"] == aid]
    assert len(actions) == 1
    assert actions[0]["latest_is_blocking"] is True
    assert board.json()["summary"]["risk_action_count"] >= 1

    # 仅有风险文案、未勾选 → 不算开放阻塞
    r = client.put(
        f"/api/test-manage/actions/{aid}/daily-updates",
        json={
            "progress_percent": 40,
            "risk_blocker": "仍有风险但非阻塞",
            "is_blocking": False,
            "progress_note": "本日进展说明已填写完毕",
        },
        headers=eng_headers,
    )
    assert r.status_code == 200, r.text
    r = client.get(f"/api/test-manage/actions/{aid}", headers=eng_headers)
    assert r.json()["latest_is_blocking"] is False


def test_clear_risk_on_newer_daily_resolves_on_board(client, auth_headers, eng_headers):
    users = _users(client, auth_headers)
    pid, did = _seed_pd(client, auth_headers, "P-clear-risk")
    task = _seed_task(client, auth_headers, pid, did, users["eng_test"]["id"])
    r = client.post(
        "/api/test-manage/actions",
        json={
            "task_id": task["id"],
            "title": "清风险",
            "owner_id": users["eng_test"]["id"],
            "publish": True,
        },
        headers=eng_headers,
    )
    aid = r.json()["id"]

    r = client.put(
        f"/api/test-manage/actions/{aid}/daily-updates",
        json={
            "progress_percent": 40,
            "risk_blocker": "环境挂了",
            "progress_note": "本日进展说明已填写完毕",
        },
        headers=eng_headers,
    )
    assert r.status_code == 200, r.text

    r = client.put(
        f"/api/test-manage/actions/{aid}/daily-updates",
        json={
            "progress_percent": 70,
            "risk_blocker": "",
            "progress_note": "本日进展说明已填写完毕",
        },
        headers=eng_headers,
    )
    assert r.status_code == 200, r.text

    r = client.get(f"/api/test-manage/actions/{aid}", headers=eng_headers)
    assert r.status_code == 200
    assert r.json()["latest_risk"] == "", r.json()["latest_risk"]

    r = client.get(
        "/api/test-manage/board",
        params={"project_id": pid},
        headers=auth_headers,
    )
    assert r.status_code == 200
    found = None
    for bt in r.json()["tasks"]:
        for a in bt["actions"]:
            if a["id"] == aid:
                found = a
    assert found is not None
    assert found["latest_risk"] == ""
    assert aid not in "".join(bt.get("risks") or [])


# ── board 历史周 ──


def test_board_week_start_filters_previous_week(client, auth_headers, eng_headers):
    users = _users(client, auth_headers)
    pid, did = _seed_pd(client, auth_headers, "P-hist-week")
    task = _seed_task(client, auth_headers, pid, did, users["eng_test"]["id"])
    r = client.post(
        "/api/test-manage/actions",
        json={
            "task_id": task["id"],
            "title": "仅本周",
            "owner_id": users["eng_test"]["id"],
            "publish": True,
        },
        headers=eng_headers,
    )
    aid = r.json()["id"]
    prev = previous_week_start()
    r = client.get(
        "/api/test-manage/board",
        params={"project_id": pid, "week_start": prev.isoformat()},
        headers=auth_headers,
    )
    assert r.status_code == 200
    ids = {a["id"] for bt in r.json()["tasks"] for a in bt["actions"]}
    assert aid not in ids


# ── 日更纪律 ──


def test_daily_requires_progress_note(client, auth_headers, eng_headers):
    users = _users(client, auth_headers)
    pid, did = _seed_pd(client, auth_headers, "P-note-req")
    task = _seed_task(client, auth_headers, pid, did, users["eng_test"]["id"])
    r = client.post(
        "/api/test-manage/actions",
        json={
            "task_id": task["id"],
            "title": "说明必填",
            "owner_id": users["eng_test"]["id"],
            "publish": True,
        },
        headers=eng_headers,
    )
    aid = r.json()["id"]
    r = client.put(
        f"/api/test-manage/actions/{aid}/daily-updates",
        json={"progress_percent": 10, "progress_note": "   "},
        headers=eng_headers,
    )
    assert r.status_code == 400
    assert "必填" in r.json()["detail"]
    r = client.put(
        f"/api/test-manage/actions/{aid}/daily-updates",
        json={"progress_percent": 10, "progress_note": "短"},
        headers=eng_headers,
    )
    assert r.status_code == 200, r.text


def test_daily_progress_cannot_decrease(client, auth_headers, eng_headers):
    users = _users(client, auth_headers)
    pid, did = _seed_pd(client, auth_headers, "P-no-regress")
    task = _seed_task(client, auth_headers, pid, did, users["eng_test"]["id"])
    r = client.post(
        "/api/test-manage/actions",
        json={
            "task_id": task["id"],
            "title": "不倒退",
            "owner_id": users["eng_test"]["id"],
            "publish": True,
        },
        headers=eng_headers,
    )
    aid = r.json()["id"]
    r = client.put(
        f"/api/test-manage/actions/{aid}/daily-updates",
        json={"progress_percent": 50, "progress_note": "本日进展说明已填写完毕"},
        headers=eng_headers,
    )
    assert r.status_code == 200
    r = client.put(
        f"/api/test-manage/actions/{aid}/daily-updates",
        json={"progress_percent": 40, "progress_note": "本日进展说明已填写完毕"},
        headers=eng_headers,
    )
    assert r.status_code == 400
    assert "不可倒退" in r.json()["detail"]


def test_daily_rejects_historical_report_date(client, auth_headers, eng_headers):
    users = _users(client, auth_headers)
    pid, did = _seed_pd(client, auth_headers, "P-no-hist")
    task = _seed_task(client, auth_headers, pid, did, users["eng_test"]["id"])
    r = client.post(
        "/api/test-manage/actions",
        json={
            "task_id": task["id"],
            "title": "仅当天",
            "owner_id": users["eng_test"]["id"],
            "publish": True,
        },
        headers=eng_headers,
    )
    aid = r.json()["id"]
    r = client.put(
        f"/api/test-manage/actions/{aid}/daily-updates",
        json={
            "report_date": "2020-01-01",
            "progress_percent": 10,
            "progress_note": "本日进展说明已填写完毕",
        },
        headers=eng_headers,
    )
    assert r.status_code == 400
    assert "当天" in r.json()["detail"]


def test_daily_locked_after_cutoff(client, auth_headers, eng_headers, monkeypatch):
    """≥19:50 后不可再写日更（测试环境需打开锁定开关）。"""
    import app.test_manage.config as tm_cfg
    import app.test_manage.service as tm_svc

    monkeypatch.setattr(tm_cfg, "DAILY_EDIT_LOCK_DISABLED", False)
    locked_at = datetime(2026, 7, 29, 19, 50, tzinfo=TM_TZ)
    monkeypatch.setattr(tm_cfg, "now_tm", lambda: locked_at)
    monkeypatch.setattr(tm_svc, "now_tm", lambda: locked_at)
    monkeypatch.setattr(tm_cfg, "today_tm", lambda: locked_at.date())
    monkeypatch.setattr(tm_svc, "today_tm", lambda: locked_at.date())

    users = _users(client, auth_headers)
    pid, did = _seed_pd(client, auth_headers, "P-lock")
    task = _seed_task(client, auth_headers, pid, did, users["eng_test"]["id"])
    r = client.post(
        "/api/test-manage/actions",
        json={
            "task_id": task["id"],
            "title": "锁定窗口",
            "owner_id": users["eng_test"]["id"],
            "publish": True,
        },
        headers=eng_headers,
    )
    aid = r.json()["id"]
    r = client.put(
        f"/api/test-manage/actions/{aid}/daily-updates",
        json={"progress_percent": 10, "progress_note": "本日进展说明已填写完毕"},
        headers=eng_headers,
    )
    assert r.status_code == 400
    assert "截止锁定" in r.json()["detail"]
    r = client.get(f"/api/test-manage/actions/{aid}", headers=eng_headers)
    assert r.json()["can_daily"] is False
