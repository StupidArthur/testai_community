"""
TM_LOOSE_MODE 权限模式双态测试：
- 默认（宽松）：所有登录角色可管理 subtask / action、编辑开发/产品人员字段
- 严格（TM_LOOSE_MODE=false）：恢复旧权限模型——仅 Admin/Manager/Task 负责人
"""
from __future__ import annotations

import pytest

TAG = "【严格模式】"
SUBTASK = "严格模式子需求"


@pytest.fixture()
def mgr_headers(client):
    r = client.post("/api/auth/login", json={"username": "manager", "password": "123456"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def lead_headers(client, auth_headers):
    """Task 负责人（Engineer）。"""
    r = client.post(
        "/api/auth/add-user",
        json={"username": "tm_strict_lead", "password": "123456", "role": "Engineer"},
        headers=auth_headers,
    )
    if r.status_code != 200:
        r = client.post(
            "/api/auth/login",
            json={"username": "tm_strict_lead", "password": "123456"},
        )
    assert r.status_code == 200, r.text
    token = r.json().get("access_token") or r.json().get("token")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def owner_headers(client, auth_headers):
    """Action 负责人（Engineer，非 Task 负责人）。"""
    r = client.post(
        "/api/auth/add-user",
        json={"username": "tm_strict_owner", "password": "123456", "role": "Engineer"},
        headers=auth_headers,
    )
    if r.status_code != 200:
        r = client.post(
            "/api/auth/login",
            json={"username": "tm_strict_owner", "password": "123456"},
        )
    assert r.status_code == 200, r.text
    token = r.json().get("access_token") or r.json().get("token")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def stranger_headers(client, auth_headers):
    """无关人员（Engineer，非负责人非 Task 负责人）。"""
    r = client.post(
        "/api/auth/add-user",
        json={"username": "tm_strict_stranger", "password": "123456", "role": "Engineer"},
        headers=auth_headers,
    )
    if r.status_code != 200:
        r = client.post(
            "/api/auth/login",
            json={"username": "tm_strict_stranger", "password": "123456"},
        )
    assert r.status_code == 200, r.text
    token = r.json().get("access_token") or r.json().get("token")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def strict_mode(monkeypatch):
    monkeypatch.setattr("app.test_manage.service.TM_LOOSE_MODE", False)


def _uid(client, headers, username: str) -> int:
    r = client.get("/api/test-manage/users", headers=headers)
    assert r.status_code == 200
    for u in r.json():
        if u["username"] == username:
            return int(u["id"])
    raise AssertionError(f"user {username} not found")


def _seed_task(client, mgr_headers, lead_id, title, name):
    """项目 + Domain + 已发布测试中 Task（带一个子需求）。"""
    r = client.post(
        "/api/test-manage/projects", json={"name": name}, headers=mgr_headers
    )
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    r = client.post(
        f"/api/test-manage/projects/{pid}/domains", json={"name": "D"}, headers=mgr_headers
    )
    assert r.status_code == 201, r.text
    did = r.json()["id"]
    r = client.post(
        "/api/test-manage/tasks",
        json={
            "project_id": pid,
            "domain_id": did,
            "title": title,
            "requirement": "需求正文",
            "module": "默认模块",
            "lead_id": lead_id,
            "tester_ids": [],
            "publish": True,
            "req_stage": "testing",
        },
        headers=mgr_headers,
    )
    assert r.status_code == 201, r.text
    task = r.json()
    # 以含子需求的 TaskOut 为准（POST subtasks 返回最新 TaskOut）
    r = client.post(
        f"/api/test-manage/tasks/{task['id']}/subtasks",
        json={"name": SUBTASK, "content": "内容"},
        headers=mgr_headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


def _create_action(client, headers, task_id, title, *, owner_id=None, publish=True):
    payload = {
        "task_id": task_id,
        "title": title,
        "subtask_name": SUBTASK,
        "publish": publish,
    }
    if owner_id is not None:
        payload["owner_id"] = owner_id
    return client.post("/api/test-manage/actions", json=payload, headers=headers)


# ── 宽松模式（默认）────────────────────────────────────────────


def test_loose_default_stranger_can_manage(client, mgr_headers, stranger_headers):
    """默认宽松模式：无关工程师可建子需求 / Action，flag 全员可见。"""
    lead_id = _uid(client, mgr_headers, "manager")
    task = _seed_task(client, mgr_headers, lead_id, "宽松-Task", f"{TAG} 宽松项目")
    r = client.post(
        f"/api/test-manage/tasks/{task['id']}/subtasks",
        json={"name": "宽松新增子需求", "content": ""},
        headers=stranger_headers,
    )
    assert r.status_code == 201, r.text
    assert r.json()["can_manage_children"] is True

    r = _create_action(client, stranger_headers, task["id"], "宽松-Action")
    assert r.status_code == 201, r.text


# ── 严格模式：subtask 管理 ────────────────────────────────────


def test_strict_subtask_crud_requires_privilege(
    client, mgr_headers, lead_headers, stranger_headers, strict_mode
):
    lead_id = _uid(client, mgr_headers, "tm_strict_lead")
    task = _seed_task(client, mgr_headers, lead_id, "严格-Subtask", f"{TAG} 子需求项目")
    tid = task["id"]
    sid = next(s["sid"] for s in task["subtasks"] if s["name"] == SUBTASK)

    # 无关人员：增 / 改 / 删 / 移动 全部 403
    r = client.post(
        f"/api/test-manage/tasks/{tid}/subtasks",
        json={"name": "严格新增子需求", "content": ""},
        headers=stranger_headers,
    )
    assert r.status_code == 403, r.text
    r = client.patch(
        f"/api/test-manage/tasks/{tid}/subtasks/{sid}",
        json={"content": "改内容"},
        headers=stranger_headers,
    )
    assert r.status_code == 403, r.text
    r = client.delete(f"/api/test-manage/tasks/{tid}/subtasks/{sid}", headers=stranger_headers)
    assert r.status_code == 403, r.text

    # Task 负责人：可增改删
    r = client.patch(
        f"/api/test-manage/tasks/{tid}/subtasks/{sid}",
        json={"dev_members": ["张开发"]},
        headers=lead_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["can_manage_children"] is True

    # flag：无关人员 False
    r = client.get(f"/api/test-manage/tasks/{tid}", headers=stranger_headers)
    assert r.status_code == 200
    assert r.json()["can_manage_children"] is False


# ── 严格模式：Action 创建 / 字段 / 状态 ───────────────────────


def test_strict_action_create_and_fields(
    client, mgr_headers, lead_headers, stranger_headers, strict_mode
):
    lead_id = _uid(client, mgr_headers, "tm_strict_lead")
    task = _seed_task(client, mgr_headers, lead_id, "严格-Action", f"{TAG} Action项目")

    # 无关人员建 Action → 403；负责人建 → 201
    r = _create_action(client, stranger_headers, task["id"], "严格-Action-A")
    assert r.status_code == 403, r.text
    r = _create_action(client, lead_headers, task["id"], "严格-Action-A", publish=False)
    assert r.status_code == 201, r.text
    aid = r.json()["id"]

    # 字段编辑：无关人员 403；负责人 200
    r = client.patch(
        f"/api/test-manage/actions/{aid}", json={"title": "改标题"}, headers=stranger_headers
    )
    assert r.status_code == 403, r.text
    r = client.patch(
        f"/api/test-manage/actions/{aid}", json={"title": "负责人改标题"}, headers=lead_headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["title"] == "负责人改标题"


def test_strict_action_status_and_members(
    client, mgr_headers, lead_headers, owner_headers, stranger_headers, strict_mode
):
    lead_id = _uid(client, mgr_headers, "tm_strict_lead")
    owner_id = _uid(client, mgr_headers, "tm_strict_owner")
    task = _seed_task(client, mgr_headers, lead_id, "严格-状态", f"{TAG} 状态项目")

    # 负责人建 Action 并指派 owner（非 Task 负责人）
    r = _create_action(client, lead_headers, task["id"], "严格-状态-A", owner_id=owner_id)
    assert r.status_code == 201, r.text
    aid = r.json()["id"]

    # 状态变更：无关人员 403；Action 负责人（旧模型允许）→ 200 发布
    r = client.patch(
        f"/api/test-manage/actions/{aid}", json={"status": "published"}, headers=stranger_headers
    )
    assert r.status_code == 403, r.text
    r = client.patch(
        f"/api/test-manage/actions/{aid}", json={"status": "published"}, headers=owner_headers
    )
    assert r.status_code == 200, r.text

    # 开发/产品人员：无关人员 403；Task 负责人 200
    r = client.patch(
        f"/api/test-manage/actions/{aid}",
        json={"dev_members": ["张开发"]},
        headers=stranger_headers,
    )
    assert r.status_code == 403, r.text
    r = client.patch(
        f"/api/test-manage/actions/{aid}",
        json={"dev_members": ["张开发"]},
        headers=lead_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["dev_members"] == ["张开发"]

    # flag：无关人员 False；Task 负责人 True
    r = client.get(f"/api/test-manage/actions/{aid}", headers=stranger_headers)
    assert r.status_code == 200
    assert r.json()["can_edit_members"] is False
    r = client.get(f"/api/test-manage/actions/{aid}", headers=lead_headers)
    assert r.status_code == 200
    assert r.json()["can_edit_members"] is True

    # 负责人改派：Action 负责人本人（非 Task 负责人）403；Task 负责人 200（留痕）
    r = client.patch(
        f"/api/test-manage/actions/{aid}", json={"owner_id": lead_id}, headers=owner_headers
    )
    assert r.status_code == 403, r.text
    r = client.patch(
        f"/api/test-manage/actions/{aid}", json={"owner_id": lead_id}, headers=lead_headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["owner_id"] == lead_id
    r = client.get(f"/api/test-manage/actions/{aid}", headers=lead_headers)
    assert r.status_code == 200
    assert any("负责人更正" in c["note"] for c in r.json()["corrections"])


def test_strict_delete_action_admin_only(
    client, mgr_headers, lead_headers, owner_headers, strict_mode
):
    lead_id = _uid(client, mgr_headers, "tm_strict_lead")
    owner_id = _uid(client, mgr_headers, "tm_strict_owner")
    task = _seed_task(client, mgr_headers, lead_id, "严格-删除", f"{TAG} 删除项目")
    r = _create_action(client, lead_headers, task["id"], "严格-删除-A", owner_id=owner_id)
    assert r.status_code == 201, r.text
    aid = r.json()["id"]

    # 严格模式：Action 负责人（非管理员）不可删
    r = client.delete(f"/api/test-manage/actions/{aid}", headers=owner_headers)
    assert r.status_code == 403, r.text
    # 管理员可删
    r = client.delete(f"/api/test-manage/actions/{aid}", headers=mgr_headers)
    assert r.status_code == 204, r.text
