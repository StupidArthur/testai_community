"""
对开发库 TPT v2.1 做现场 API 回归（【回归】前缀数据）。

用法：后端已启动后
  python scripts/tm_live_regression_tpt.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import requests

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

BASE = "http://127.0.0.1:48010/api"
TAG = "【回归】"
PASS = "123456"


class Failures(list):
    def check(self, ok: bool, name: str, detail: str = "") -> None:
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))
        if not ok:
            self.append(f"{name}: {detail}")


def login(username: str, password: str) -> tuple[dict, dict]:
    r = requests.post(f"{BASE}/auth/login", json={"username": username, "password": password})
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, r.json()["user"]


def ensure_user(admin_h: dict, fails: Failures, uname: str, rn: str) -> None:
    r = requests.post(
        f"{BASE}/auth/add-user",
        json={"username": uname, "password": PASS, "role": "Engineer", "real_name": rn},
        headers=admin_h,
    )
    if r.status_code not in (200, 400):
        fails.check(False, f"create {uname}", r.text[:120])


def main() -> int:
    fails = Failures()
    admin_h, admin = login("admin", "admin")
    mgr_h, mgr = login("manager", PASS)

    for uname, rn in (
        ("tm_live_lead", "现场Lead"),
        ("tm_live_owner", "现场Owner"),
        ("tm_live_tester", "现场Tester"),
        ("tm_live_x", "现场路人"),
    ):
        ensure_user(admin_h, fails, uname, rn)

    lead_h, lead = login("tm_live_lead", PASS)
    owner_h, owner = login("tm_live_owner", PASS)
    tester_h, tester = login("tm_live_tester", PASS)
    x_h, xuser = login("tm_live_x", PASS)

    projects = requests.get(f"{BASE}/test-manage/projects", headers=mgr_h).json()
    tpt = next((p for p in projects if p.get("name") == "TPT v2.1"), None)
    fails.check(tpt is not None, "找到 TPT v2.1", str([p.get("name") for p in projects][:5]))
    if not tpt:
        return 1
    pid = tpt["id"]
    domains = requests.get(f"{BASE}/test-manage/projects/{pid}/domains", headers=mgr_h).json()
    fails.check(len(domains) >= 1, "TPT 已有 Domain", str(len(domains)))
    did = domains[0]["id"]
    dname = domains[0]["name"]
    did2 = domains[1]["id"] if len(domains) > 1 else did

    # ── 1. Task 权限与空看板 ──
    r = requests.post(
        f"{BASE}/test-manage/tasks",
        json={
            "project_id": pid,
            "domain_id": did,
            "title": f"{TAG} 现场Task-{dname}",
            "requirement": "现场回归",
            "lead_id": lead["id"],
            "tester_ids": [owner["id"], tester["id"]],
            "publish": True,
            "req_stage": "testing",
        },
        headers=mgr_h,
    )
    fails.check(r.status_code == 201, "Manager 在 TPT Domain 建 Task", r.text[:160])
    if r.status_code != 201:
        return 1
    task = r.json()
    tid = task["id"]

    r = requests.patch(f"{BASE}/test-manage/tasks/{tid}", json={"title": "hack"}, headers=x_h)
    fails.check(r.status_code == 403, "路人不可改 Task", str(r.status_code))

    r = requests.patch(
        f"{BASE}/test-manage/tasks/{tid}",
        json={"requirement": "lead更新", "change_summary": "现场"},
        headers=lead_h,
    )
    fails.check(r.status_code == 200, "Lead 可改 Task", r.text[:120])

    detail = requests.get(f"{BASE}/test-manage/tasks/{tid}", headers=lead_h).json()
    logs = detail.get("update_logs") or []
    fails.check(any("现场" in (x.get("summary") or "") for x in logs), "Task 更新日志写入")

    board = requests.get(f"{BASE}/test-manage/board", params={"project_id": pid}, headers=lead_h).json()
    hit = next((b for b in board.get("tasks", []) if b["task"]["id"] == tid), None)
    fails.check(hit is not None and hit["actions"] == [], "空周 Task 出现在看板(Lead)", str(hit is not None))

    board_x = requests.get(f"{BASE}/test-manage/board", params={"project_id": pid}, headers=x_h).json()
    hit_x = next((b for b in board_x.get("tasks", []) if b["task"]["id"] == tid), None)
    fails.check(hit_x is None, "路人看不到无关空 Task", str(hit_x is not None))

    # ── 2. Action 生命周期 ──
    r = requests.post(
        f"{BASE}/test-manage/actions",
        json={
            "task_id": tid,
            "title": f"{TAG} 现场Action",
            "owner_id": owner["id"],
            "test_content": "测",
            "publish": False,
        },
        headers=lead_h,
    )
    fails.check(r.status_code == 201, "Lead 建草稿 Action", r.text[:160])
    aid = r.json()["id"] if r.status_code == 201 else None

    if aid:
        r = requests.patch(
            f"{BASE}/test-manage/actions/{aid}",
            json={"title": "tester改草稿"},
            headers=tester_h,
        )
        fails.check(r.status_code == 403, "Tester 非 Lead 不可改草稿字段", str(r.status_code))

        r = requests.patch(
            f"{BASE}/test-manage/actions/{aid}",
            json={"title": "owner改草稿"},
            headers=owner_h,
        )
        fails.check(r.status_code == 403, "Owner 不可改草稿字段", str(r.status_code))

        r = requests.patch(
            f"{BASE}/test-manage/actions/{aid}",
            json={"status": "published"},
            headers=owner_h,
        )
        fails.check(r.status_code == 200, "Owner 可发布自己的草稿", r.text[:120])

        r = requests.put(
            f"{BASE}/test-manage/actions/{aid}/daily-updates",
            json={"progress_percent": 20, "risk_blocker": "现场风险UNIQUE", "progress_note": "推进"},
            headers=owner_h,
        )
        fails.check(r.status_code == 200, "Owner 日更", r.text[:120])

        r = requests.put(
            f"{BASE}/test-manage/actions/{aid}/daily-updates",
            json={"progress_percent": 20, "risk_blocker": "现场风险UNIQUE", "progress_note": "推进"},
            headers=lead_h,
        )
        fails.check(r.status_code == 403, "Lead 不可代写日更", str(r.status_code))

        r = requests.put(
            f"{BASE}/test-manage/actions/{aid}/daily-updates",
            json={"progress_percent": 25, "risk_blocker": "现场风险UNIQUE", "progress_note": "mgr代"},
            headers=mgr_h,
        )
        fails.check(r.status_code == 200, "Manager 可代写日更", r.text[:120])

        r = requests.put(
            f"{BASE}/test-manage/actions/{aid}/daily-updates",
            json={"progress_percent": 15, "risk_blocker": "", "progress_note": "回退"},
            headers=owner_h,
        )
        fails.check(r.status_code == 400, "进度不可回退", str(r.status_code))

        r = requests.put(
            f"{BASE}/test-manage/actions/{aid}/daily-updates",
            json={"progress_percent": 30, "risk_blocker": "", "progress_note": "   "},
            headers=owner_h,
        )
        fails.check(r.status_code == 400, "空进度说明拒绝", str(r.status_code))

        r = requests.put(
            f"{BASE}/test-manage/actions/{aid}/daily-updates",
            json={"progress_percent": 30, "risk_blocker": "", "progress_note": "已解除风险"},
            headers=owner_h,
        )
        fails.check(r.status_code == 200, "清空风险日更", r.text[:120])
        detail_a = requests.get(f"{BASE}/test-manage/actions/{aid}", headers=owner_h).json()
        fails.check((detail_a.get("latest_risk") or "") == "", "latest_risk 已清空")

        r = requests.post(
            f"{BASE}/test-manage/actions/{aid}/corrections",
            json={"note": "owner更正一条"},
            headers=owner_h,
        )
        fails.check(r.status_code in (200, 201), "Owner 更正", r.text[:120])

        r = requests.post(
            f"{BASE}/test-manage/actions/{aid}/corrections",
            json={"note": "路人更正"},
            headers=x_h,
        )
        fails.check(r.status_code == 403, "路人不可更正", str(r.status_code))

        r = requests.post(
            f"{BASE}/test-manage/actions/{aid}/corrections",
            json={"note": "tester更正他人"},
            headers=tester_h,
        )
        fails.check(r.status_code == 403, "Tester 不可更正他人 Action", str(r.status_code))

        r = requests.patch(
            f"{BASE}/test-manage/actions/{aid}",
            json={"status": "cancelled"},
            headers=mgr_h,
        )
        fails.check(r.status_code == 400, "Action 禁止取消", str(r.status_code))

        # clone
        r = requests.post(
            f"{BASE}/test-manage/actions/{aid}/clone",
            json={"publish": False},
            headers=lead_h,
        )
        fails.check(r.status_code == 201, "clone 本周/上周", r.text[:120])
        if r.status_code == 201:
            fails.check((r.json().get("latest_risk") or "") == "", "clone 不带风险")
            fails.check(r.json().get("status") == "draft", "clone 默认草稿")

        # tester 自己的 Action
        r = requests.post(
            f"{BASE}/test-manage/actions",
            json={
                "task_id": tid,
                "title": f"{TAG} Tester自己的",
                "owner_id": tester["id"],
                "publish": True,
            },
            headers=lead_h,
        )
        fails.check(r.status_code == 201, "Lead 给 Tester 建 Action", r.text[:120])
        aid_t = r.json()["id"] if r.status_code == 201 else None
        if aid_t:
            r = requests.put(
                f"{BASE}/test-manage/actions/{aid_t}/daily-updates",
                json={"progress_percent": 10, "risk_blocker": "", "progress_note": "tester自己的日更"},
                headers=tester_h,
            )
            fails.check(r.status_code == 200, "Tester 可日更自己的 Action", r.text[:120])
            r = requests.put(
                f"{BASE}/test-manage/actions/{aid}/daily-updates",
                json={"progress_percent": 35, "risk_blocker": "", "progress_note": "越权"},
                headers=tester_h,
            )
            fails.check(r.status_code == 403, "Tester 不可日更他人 Action", str(r.status_code))

        # mine
        mine_o = requests.get(f"{BASE}/test-manage/actions/mine", headers=owner_h).json()
        mine_ids = {a["id"] for a in mine_o}
        fails.check(aid in mine_ids, "mine 含 Owner 自己的")
        if aid_t:
            fails.check(aid_t not in mine_ids, "mine 不含他人的")

        # 完成：未满 100 拒绝
        r = requests.patch(
            f"{BASE}/test-manage/actions/{aid}",
            json={"status": "done"},
            headers=owner_h,
        )
        fails.check(r.status_code == 400, "进度未满不可完成", str(r.status_code))

        requests.put(
            f"{BASE}/test-manage/actions/{aid}/daily-updates",
            json={"progress_percent": 100, "risk_blocker": "", "progress_note": "收尾"},
            headers=owner_h,
        )
        r = requests.patch(
            f"{BASE}/test-manage/actions/{aid}",
            json={"status": "done"},
            headers=owner_h,
        )
        fails.check(r.status_code == 200, "100% 后可完成", r.text[:120])
        r = requests.put(
            f"{BASE}/test-manage/actions/{aid}/daily-updates",
            json={"progress_percent": 100, "risk_blocker": "", "progress_note": "完成后"},
            headers=owner_h,
        )
        fails.check(r.status_code == 403, "完成后不可日更", str(r.status_code))

    # Tester 不可建 Action
    r = requests.post(
        f"{BASE}/test-manage/actions",
        json={"task_id": tid, "title": f"{TAG} tester建", "owner_id": tester["id"]},
        headers=tester_h,
    )
    fails.check(r.status_code == 403, "Tester 不可建 Action", str(r.status_code))

    # ── 3. 已完成 Task ──
    r = requests.post(
        f"{BASE}/test-manage/tasks",
        json={
            "project_id": pid,
            "domain_id": did2,
            "title": f"{TAG} 已完成Task",
            "requirement": "x",
            "lead_id": lead["id"],
            "tester_ids": [],
            "publish": True,
            "req_stage": "testing",
        },
        headers=mgr_h,
    )
    tid2 = r.json()["id"]
    requests.patch(
        f"{BASE}/test-manage/tasks/{tid2}",
        json={"status": "done", "change_summary": "done"},
        headers=mgr_h,
    )
    r = requests.post(
        f"{BASE}/test-manage/actions",
        json={"task_id": tid2, "title": f"{TAG} 不应", "owner_id": lead["id"]},
        headers=lead_h,
    )
    fails.check(r.status_code == 400, "已完成 Task 不可建 Action", str(r.status_code))
    detail2 = requests.get(f"{BASE}/test-manage/tasks/{tid2}", headers=lead_h).json()
    fails.check(detail2.get("can_add_action") is False, "done Task can_add_action=false")

    # ── 4. 转让 Lead ──
    r = requests.post(
        f"{BASE}/test-manage/tasks",
        json={
            "project_id": pid,
            "domain_id": did,
            "title": f"{TAG} 转让Lead",
            "requirement": "t",
            "lead_id": lead["id"],
            "tester_ids": [owner["id"]],
            "publish": True,
        },
        headers=mgr_h,
    )
    tid3 = r.json()["id"]
    r = requests.patch(
        f"{BASE}/test-manage/tasks/{tid3}",
        json={"lead_id": owner["id"], "change_summary": "转让给owner"},
        headers=lead_h,
    )
    fails.check(r.status_code == 200, "Lead 可转让负责人", r.text[:120])
    if r.status_code == 200:
        fails.check(r.json().get("lead_id") == owner["id"], "转让后 lead_id 正确")
        r = requests.patch(
            f"{BASE}/test-manage/tasks/{tid3}",
            json={"title": "旧lead改"},
            headers=lead_h,
        )
        fails.check(r.status_code == 403, "转让后旧 Lead 不可再改", str(r.status_code))

    # ── 5. 推送 dry_run ──
    r = requests.post(f"{BASE}/test-manage/push/daily", json={"dry_run": True}, headers=x_h)
    fails.check(r.status_code == 403, "Engineer 不可推送", str(r.status_code))
    r = requests.post(f"{BASE}/test-manage/push/daily", json={"dry_run": True}, headers=mgr_h)
    fails.check(r.status_code == 200 and (r.json().get("message") or ""), "Manager 日报 dry_run")
    dmsg = (r.json().get("message") or "") if r.status_code == 200 else ""
    fails.check(len(dmsg) > 20, "日报内容非空", str(len(dmsg)))

    r = requests.post(f"{BASE}/test-manage/push/weekly", json={"dry_run": True}, headers=mgr_h)
    fails.check(r.status_code == 200 and (r.json().get("message") or ""), "Manager 周报 dry_run")
    wmsg = (r.json().get("message") or "") if r.status_code == 200 else ""
    fails.check(("周报" in wmsg) or ("Task" in wmsg) or ("Action" in wmsg), "周报文案含关键词")

    r = requests.post(f"{BASE}/test-manage/push/daily", json={"dry_run": True}, headers=admin_h)
    fails.check(r.status_code == 200, "Admin 也可日报 dry_run", str(r.status_code))

    print("")
    print(f"FAIL count: {len(fails)}")
    for f in fails:
        print(" -", f)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
