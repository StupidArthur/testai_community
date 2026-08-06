"""
周三切周回归：日更/看板/新建 Action / 推送所属周口径。

规则摘要（UTC+8）：
- current_week_start：≥周三 17:00 进入「新一周」
- daily_context_week_start：周三全天仍用「刚结束周」（this_wed_17 - 7d）
  → 切周后新建的 Action 属新周，当天不可日更；仍应写旧周 Action 的日更
"""
from __future__ import annotations

from datetime import datetime

import pytest

from app.platform.database import SessionLocal
from app.test_manage.config import TM_TZ
from app.test_manage.week import (
    current_week_start,
    daily_context_week_start,
    week_key,
)
from app.test_manage import push_report as report


TAG = "【切周】"

# 固定锚点：2026-07-15 为周三
WED_BEFORE = datetime(2026, 7, 15, 16, 59, tzinfo=TM_TZ)
WED_AT = datetime(2026, 7, 15, 17, 0, tzinfo=TM_TZ)
WED_AFTER = datetime(2026, 7, 15, 18, 30, tzinfo=TM_TZ)
THU = datetime(2026, 7, 16, 10, 0, tzinfo=TM_TZ)
OLD_WEEK = datetime(2026, 7, 8, 17, 0, tzinfo=TM_TZ)
NEW_WEEK = datetime(2026, 7, 15, 17, 0, tzinfo=TM_TZ)


# ── 纯函数口径 ──────────────────────────────────────────────


def test_w_daily_context_wed_all_day_stays_on_ending_week():
    assert daily_context_week_start(WED_BEFORE) == OLD_WEEK
    assert daily_context_week_start(WED_AT) == OLD_WEEK
    assert daily_context_week_start(WED_AFTER) == OLD_WEEK
    assert current_week_start(WED_BEFORE) == OLD_WEEK
    assert current_week_start(WED_AT) == NEW_WEEK
    assert current_week_start(WED_AFTER) == NEW_WEEK


def test_w_daily_context_non_wed_matches_current():
    assert daily_context_week_start(THU) == current_week_start(THU) == NEW_WEEK


# ── fixtures / helpers ───────────────────────────────────────


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
    if r.status_code != 200:
        r = client.post("/api/auth/login", json={"username": username, "password": "123456"})
    assert r.status_code == 200, r.text
    body = r.json()
    token = body.get("access_token")
    if not token:
        r = client.post("/api/auth/login", json={"username": username, "password": "123456"})
        assert r.status_code == 200
        token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def lead_headers(client, auth_headers):
    return _ensure_user(client, auth_headers, "tm_lead", "回归Lead")


@pytest.fixture()
def owner_headers(client, auth_headers):
    return _ensure_user(client, auth_headers, "tm_owner", "回归Owner")


def _uid(client, headers, username: str) -> int:
    r = client.get("/api/test-manage/users", headers=headers)
    assert r.status_code == 200
    for u in r.json():
        if u["username"] == username:
            return int(u["id"])
    raise AssertionError(username)


def _install_clock(monkeypatch, when: datetime) -> None:
    """把业务时钟钉在 when；同步 patch week/service/push_* 的周函数绑定。"""
    import app.test_manage.week as w
    import app.test_manage.service as s
    import app.test_manage.config as c
    import app.test_manage.push_report as pr
    import app.test_manage.push_service as ps

    real_cws = w.current_week_start
    real_dws = w.daily_context_week_start
    real_pws = w.previous_week_start

    def cws(now=None):
        return real_cws(when if now is None else now)

    def dws(now=None):
        return real_dws(when if now is None else now)

    def pws(week_start=None):
        return real_pws(week_start if week_start is not None else cws())

    for mod in (w, s, pr, ps):
        monkeypatch.setattr(mod, "current_week_start", cws, raising=False)
        monkeypatch.setattr(mod, "daily_context_week_start", dws, raising=False)
        monkeypatch.setattr(mod, "previous_week_start", pws, raising=False)

    monkeypatch.setattr(c, "now_tm", lambda: when)
    monkeypatch.setattr(s, "now_tm", lambda: when)
    monkeypatch.setattr(c, "today_tm", lambda: when.date())
    monkeypatch.setattr(s, "today_tm", lambda: when.date())


def _sandbox(client, mgr_headers):
    r = client.post(
        "/api/test-manage/projects",
        json={"name": f"{TAG} P", "description": "cutover"},
        headers=mgr_headers,
    )
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    r = client.post(
        f"/api/test-manage/projects/{pid}/domains",
        json={"name": "平台"},
        headers=mgr_headers,
    )
    assert r.status_code == 201, r.text
    return pid, r.json()["id"]


def _task(client, headers, pid, did, lead_id, title, tester_ids=None):
    r = client.post(
        "/api/test-manage/tasks",
        json={
            "project_id": pid,
            "domain_id": did,
            "title": title,
            "requirement": "r",
            "lead_id": lead_id,
            "tester_ids": tester_ids or [],
            "publish": True,
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


def _action(client, headers, tid, title, owner_id, publish=True):
    r = client.post(
        "/api/test-manage/actions",
        json={
            "task_id": tid,
            "title": title,
            "owner_id": owner_id,
            "publish": publish,
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


def _force_action_week(action_id: str, ws: datetime) -> None:
    db = SessionLocal()
    try:
        from app.test_manage.models import TmAction

        row = db.query(TmAction).filter(TmAction.id == action_id).one()
        row.week_start = ws
        row.week_key = week_key(ws)
        db.commit()
    finally:
        db.close()


# ── API：切周后日更只写刚结束周 ─────────────────────────────


def test_w_after_cutover_daily_only_on_old_week_action(
    client, mgr_headers, lead_headers, owner_headers, monkeypatch
):
    """周三 19:30：新周 Action 不可日更；旧周 Action 可日更。"""
    _install_clock(monkeypatch, WED_AFTER)
    pid, did = _sandbox(client, mgr_headers)
    lead_id = _uid(client, mgr_headers, "tm_lead")
    owner_id = _uid(client, mgr_headers, "tm_owner")
    task = _task(client, mgr_headers, pid, did, lead_id, f"{TAG} 切后", [owner_id])

    # 先造「旧周」Action（再钉时钟创建会进新周，故强制改 week）
    old_act = _action(client, lead_headers, task["id"], f"{TAG} 旧周A", owner_id)
    _force_action_week(old_act["id"], OLD_WEEK)

    new_act = _action(client, lead_headers, task["id"], f"{TAG} 新周A", owner_id)
    assert new_act["week_key"] == week_key(NEW_WEEK)

    r = client.put(
        f"/api/test-manage/actions/{new_act['id']}/daily-updates",
        json={"progress_percent": 10, "risk_blocker": "", "progress_note": "新周不可写"},
        headers=owner_headers,
    )
    assert r.status_code == 400, r.text
    assert "汇报周" in (r.json().get("detail") or "") or "周" in (r.json().get("detail") or "")

    r = client.put(
        f"/api/test-manage/actions/{old_act['id']}/daily-updates",
        json={"progress_percent": 40, "risk_blocker": "切周风险", "progress_note": "旧周可写"},
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text


def test_w_before_cutover_daily_on_current_week(
    client, mgr_headers, lead_headers, owner_headers, monkeypatch
):
    """周三 17:59：仍属旧周，新建 Action 可日更。"""
    _install_clock(monkeypatch, WED_BEFORE)
    pid, did = _sandbox(client, mgr_headers)
    lead_id = _uid(client, mgr_headers, "tm_lead")
    owner_id = _uid(client, mgr_headers, "tm_owner")
    task = _task(client, mgr_headers, pid, did, lead_id, f"{TAG} 切前", [owner_id])
    act = _action(client, lead_headers, task["id"], f"{TAG} 切前A", owner_id)
    assert act["week_key"] == week_key(OLD_WEEK)
    r = client.put(
        f"/api/test-manage/actions/{act['id']}/daily-updates",
        json={"progress_percent": 15, "risk_blocker": "", "progress_note": "切前正常"},
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text


def test_w_board_after_cutover_is_new_week(
    client, mgr_headers, lead_headers, owner_headers, monkeypatch
):
    """切周后默认看板看新周；旧周 Action 不出现在默认看板。"""
    _install_clock(monkeypatch, WED_AFTER)
    pid, did = _sandbox(client, mgr_headers)
    lead_id = _uid(client, mgr_headers, "tm_lead")
    owner_id = _uid(client, mgr_headers, "tm_owner")
    task = _task(client, mgr_headers, pid, did, lead_id, f"{TAG} 看板", [owner_id])
    old_act = _action(client, lead_headers, task["id"], f"{TAG} 旧", owner_id)
    _force_action_week(old_act["id"], OLD_WEEK)
    new_act = _action(client, lead_headers, task["id"], f"{TAG} 新", owner_id)

    board = client.get(
        "/api/test-manage/board", params={"project_id": pid}, headers=mgr_headers
    ).json()
    assert board["week_key"] == week_key(NEW_WEEK)
    hit = next(b for b in board["tasks"] if b["task"]["id"] == task["id"])
    ids = {a["id"] for a in hit["actions"]}
    assert new_act["id"] in ids
    assert old_act["id"] not in ids

    # 历史周可看旧 Action
    hist = client.get(
        "/api/test-manage/board",
        params={"project_id": pid, "week_start": OLD_WEEK.isoformat()},
        headers=mgr_headers,
    ).json()
    hit_h = next(b for b in hist["tasks"] if b["task"]["id"] == task["id"])
    assert any(a["id"] == old_act["id"] for a in hit_h["actions"])


def test_w_empty_task_highlight_on_new_week_board(
    client, mgr_headers, lead_headers, monkeypatch
):
    """切周后空 Task 仍出现在新周看板（便于补建）。"""
    _install_clock(monkeypatch, WED_AFTER)
    pid, did = _sandbox(client, mgr_headers)
    lead_id = _uid(client, mgr_headers, "tm_lead")
    task = _task(client, mgr_headers, pid, did, lead_id, f"{TAG} 空新周")
    board = client.get(
        "/api/test-manage/board", params={"project_id": pid}, headers=lead_headers
    ).json()
    hit = next(b for b in board["tasks"] if b["task"]["id"] == task["id"])
    assert hit["actions"] == []
    assert hit["task"]["can_add_action"] is True


def test_w_clone_candidates_after_cutover_are_previous_week(
    client, mgr_headers, lead_headers, owner_headers, monkeypatch
):
    """切周后 clone-candidates = previous_week = 刚结束周。"""
    _install_clock(monkeypatch, WED_AFTER)
    pid, did = _sandbox(client, mgr_headers)
    lead_id = _uid(client, mgr_headers, "tm_lead")
    owner_id = _uid(client, mgr_headers, "tm_owner")
    task = _task(client, mgr_headers, pid, did, lead_id, f"{TAG} 候选", [owner_id])
    old_act = _action(client, lead_headers, task["id"], f"{TAG} 候选A", owner_id)
    _force_action_week(old_act["id"], OLD_WEEK)
    # 新周再建一条，不应进候选
    _action(client, lead_headers, task["id"], f"{TAG} 本周不候选", owner_id)

    cands = client.get(
        f"/api/test-manage/tasks/{task['id']}/clone-candidates", headers=lead_headers
    ).json()
    ids = {c["id"] for c in cands}
    assert old_act["id"] in ids
    assert all(c["week_key"] == week_key(OLD_WEEK) for c in cands if c["id"] == old_act["id"])

    cloned = client.post(
        f"/api/test-manage/actions/{old_act['id']}/clone",
        json={"publish": False},
        headers=lead_headers,
    )
    assert cloned.status_code == 201
    assert cloned.json()["week_key"] == week_key(NEW_WEEK)
    assert (cloned.json().get("latest_risk") or "") == ""


def test_w_after_cutover_daily_lock_still_applies(
    client, mgr_headers, lead_headers, owner_headers, monkeypatch
):
    """切周后周三 19:51：旧周 Action 可写窗口仍受 19:50 锁定。"""
    _install_clock(monkeypatch, datetime(2026, 7, 15, 19, 51, tzinfo=TM_TZ))
    import app.test_manage.config as cfg

    monkeypatch.setattr(cfg, "DAILY_EDIT_LOCK_DISABLED", False)

    pid, did = _sandbox(client, mgr_headers)
    lead_id = _uid(client, mgr_headers, "tm_lead")
    owner_id = _uid(client, mgr_headers, "tm_owner")
    task = _task(client, mgr_headers, pid, did, lead_id, f"{TAG} 锁交叉", [owner_id])
    old_act = _action(client, lead_headers, task["id"], f"{TAG} 锁旧", owner_id)
    _force_action_week(old_act["id"], OLD_WEEK)

    r = client.put(
        f"/api/test-manage/actions/{old_act['id']}/daily-updates",
        json={"progress_percent": 10, "risk_blocker": "", "progress_note": "锁后"},
        headers=owner_headers,
    )
    assert r.status_code == 400
    assert "截止" in (r.json().get("detail") or "")


def test_w_push_dry_run_uses_daily_context_week(
    client, mgr_headers, lead_headers, owner_headers, monkeypatch
):
    """切周后日报 dry_run 统计刚结束周的风险，不含仅存在于新周的风险。"""
    _install_clock(monkeypatch, WED_AFTER)
    # 关闭日更锁定，避免 19:30 挡日更
    import app.test_manage.config as cfg

    monkeypatch.setattr(cfg, "DAILY_EDIT_LOCK_DISABLED", True)

    pid, did = _sandbox(client, mgr_headers)
    lead_id = _uid(client, mgr_headers, "tm_lead")
    owner_id = _uid(client, mgr_headers, "tm_owner")
    task = _task(client, mgr_headers, pid, did, lead_id, f"{TAG} 推送", [owner_id])

    old_act = _action(client, lead_headers, task["id"], f"{TAG} 旧风险Act", owner_id)
    _force_action_week(old_act["id"], OLD_WEEK)
    r = client.put(
        f"/api/test-manage/actions/{old_act['id']}/daily-updates",
        json={
            "progress_percent": 55,
            "risk_blocker": "旧周独特词CUTOVER_OLD",
            "progress_note": "旧",
        },
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text

    new_act = _action(client, lead_headers, task["id"], f"{TAG} 新风险Act", owner_id)
    # 新周 Action 不能日更；用 DB 无法直接写日更到「今天」且属新周——跳过，只断言旧词在推送里
    db = SessionLocal()
    try:
        risks = report.collect_open_risks(db, week_start=daily_context_week_start(WED_AFTER))
        texts = " ".join((v.risk or "") for v in risks.values())
        assert "CUTOVER_OLD" in texts
    finally:
        db.close()

    daily = client.post(
        "/api/test-manage/push/daily", json={"dry_run": True}, headers=mgr_headers
    )
    assert daily.status_code == 200, daily.text
    msg = daily.json().get("message") or ""
    assert "CUTOVER_OLD" in msg
    assert new_act["title"]  # sanity: 新周 Action 已创建
