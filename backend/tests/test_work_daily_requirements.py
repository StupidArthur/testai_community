"""
工作日报需求验收测试（师兄需求文档）。

REQ-1 导航「工作日报」        → 前端 AppLayout / router（手工项）
REQ-2 列表 + 新建             → GET /work-daily
REQ-3 审核/提交/角色/Skill    → POST audit / submit
REQ-4 Admin 按日导出          → GET export
"""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai_service.work_daily.constants import WORK_DAILY_SKILL_NAME, REPORT_ROLES
from app.ai_service.work_daily.models import WorkDailyAuditResult, WorkItem
from app.skill_hub.skill_ref import ResolveMode

MOCK_AUDIT_OK = WorkDailyAuditResult(
    valid=True,
    work_items=[WorkItem(category="功能测试", description="联调", hours=6.0, ratio=1.0)],
    total_hours=6.0,
    dimension_coverage=["功能测试"],
    summary="完成联调",
)

MOCK_AUDIT_INCOMPLETE = WorkDailyAuditResult(
    valid=False,
    validation_issues=["缺少各工作项的投入时间"],
    suggestions=["请补充每项工作花费的小时数"],
    missing_dimensions=["工时"],
    summary="信息不完整",
)

# service 层 import 入口，patch 此处可拦截 audit/submit
PATCH_AUDIT = "app.daily_report.service.audit_work_daily"


@pytest.fixture(autouse=True)
def _ensure_skill(client):
    from app.daily_report.bootstrap import ensure_work_daily_skill

    ensure_work_daily_skill()


def _today_str() -> str:
    return date.today().isoformat()


def _payload(**kw) -> dict:
    base = {
        "report_date": _today_str(),
        "report_role": "测试工程师",
        "raw_text": "功能测试 6 小时，接口回归 2 小时，合计 8 小时。",
    }
    base.update(kw)
    return base


class TestReq2ListAndCreate:
    """REQ-2：登录用户可查看自己的日报列表。"""

    def test_list_after_submit(self, client, eng_headers):
        with patch(PATCH_AUDIT, new_callable=AsyncMock, return_value=(MOCK_AUDIT_OK, "v1")):
            assert client.post("/api/work-daily", json=_payload(), headers=eng_headers).status_code == 201
        lst = client.get("/api/work-daily", headers=eng_headers)
        assert lst.status_code == 200
        assert len(lst.json()) >= 1
        assert "功能测试" in lst.json()[0]["summary_preview"]


class TestReq3AuditAndSubmit:
    """REQ-3：审核与提交分离；角色；master Skill；可忽略审核直接提交。"""

    def test_audit_not_persisted(self, client, eng_headers):
        before = len(client.get("/api/work-daily", headers=eng_headers).json())
        with patch(PATCH_AUDIT, new_callable=AsyncMock, return_value=(MOCK_AUDIT_INCOMPLETE, "v1")):
            r = client.post("/api/work-daily/audit", json=_payload(), headers=eng_headers)
        assert r.status_code == 200
        assert r.json()["audit"]["valid"] is False
        after = len(client.get("/api/work-daily", headers=eng_headers).json())
        assert after == before

    def test_audit_uses_master_skill(self, client, eng_headers):
        resolved = MagicMock(payload="system prompt", version_id="master-v1")
        with patch("app.ai_service.work_daily.audit.resolve_skill_ref", return_value=resolved) as mock_ref:
            with patch(
                "app.ai_service.work_daily.audit.chat",
                new_callable=AsyncMock,
                return_value=MOCK_AUDIT_OK.model_dump_json(),
            ):
                assert client.post("/api/work-daily/audit", json=_payload(), headers=eng_headers).status_code == 200
        ref_arg = mock_ref.call_args[0][1]
        assert ref_arg.branch_type == "master"
        assert ref_arg.resolve_mode == ResolveMode.branch_head

    def test_incomplete_audit_returns_suggestions(self, client, eng_headers):
        with patch(PATCH_AUDIT, new_callable=AsyncMock, return_value=(MOCK_AUDIT_INCOMPLETE, "v1")):
            audit = client.post("/api/work-daily/audit", json=_payload(raw_text="今天很忙"), headers=eng_headers).json()["audit"]
        assert audit["valid"] is False
        assert audit["suggestions"] or audit["validation_issues"]
        assert audit["missing_dimensions"]

    @pytest.mark.parametrize("role", REPORT_ROLES)
    def test_report_roles(self, client, eng_headers, role):
        with patch(PATCH_AUDIT, new_callable=AsyncMock, return_value=(MOCK_AUDIT_OK, "v1")):
            assert client.post("/api/work-daily/audit", json=_payload(report_role=role), headers=eng_headers).status_code == 200

    def test_invalid_role_rejected(self, client, eng_headers):
        assert client.post("/api/work-daily/audit", json=_payload(report_role="开发工程师"), headers=eng_headers).status_code == 422

    def test_submit_without_prior_audit_calls_llm(self, client, eng_headers):
        with patch(PATCH_AUDIT, new_callable=AsyncMock, return_value=(MOCK_AUDIT_OK, "v1")) as mock_audit:
            assert client.post("/api/work-daily", json=_payload(), headers=eng_headers).status_code == 201
        mock_audit.assert_called_once()

    def test_submit_with_audit_snapshot_skips_llm(self, client, eng_headers):
        with patch(PATCH_AUDIT, new_callable=AsyncMock) as mock_audit:
            r = client.post(
                "/api/work-daily",
                json={**_payload(raw_text="忽略审核直接提交 8h"), "audit": MOCK_AUDIT_INCOMPLETE.model_dump()},
                headers=eng_headers,
            )
        assert r.status_code == 201
        mock_audit.assert_not_called()
        assert r.json()["audit"]["valid"] is False

    def test_reaudit_multiple_times(self, client, eng_headers):
        with patch(
            PATCH_AUDIT,
            new_callable=AsyncMock,
            side_effect=[(MOCK_AUDIT_INCOMPLETE, "v1"), (MOCK_AUDIT_OK, "v1")],
        ):
            r1 = client.post("/api/work-daily/audit", json=_payload(), headers=eng_headers)
            r2 = client.post("/api/work-daily/audit", json=_payload(raw_text="功能测试 8h"), headers=eng_headers)
        assert r1.json()["audit"]["valid"] is False
        assert r2.json()["audit"]["valid"] is True


class TestReq4AdminExport:
    """REQ-4：Admin 按日期批量导出全员日报。"""

    def test_admin_export_all_engineers_on_date(self, client, auth_headers, eng_headers):
        d = _today_str()
        with patch(PATCH_AUDIT, new_callable=AsyncMock, return_value=(MOCK_AUDIT_OK, "v1")):
            client.post("/api/work-daily", json=_payload(report_date=d), headers=eng_headers)
        rows = client.get("/api/work-daily/export", params={"report_date": d}, headers=auth_headers).json()
        assert len(rows) >= 1
        assert rows[0]["username"] == "eng_test"
        assert rows[0]["audit"]["work_items"]

    def test_engineer_cannot_export(self, client, eng_headers):
        assert client.get("/api/work-daily/export", params={"report_date": _today_str()}, headers=eng_headers).status_code == 403

    def test_admin_export_empty_date(self, client, auth_headers):
        r = client.get("/api/work-daily/export", params={"report_date": "2099-01-01"}, headers=auth_headers)
        assert r.status_code == 200
        assert r.json() == []


class TestReqPermissions:
    def test_engineer_cannot_read_others_report(self, client, auth_headers, eng_headers):
        d = (date.today() - timedelta(days=2)).isoformat()
        with patch(PATCH_AUDIT, new_callable=AsyncMock, return_value=(MOCK_AUDIT_OK, "v1")):
            rid = client.post("/api/work-daily", json=_payload(report_date=d), headers=eng_headers).json()["id"]
        token2 = client.post(
            "/api/auth/add-user",
            json={"username": "eng2_req", "password": "eng123456", "role": "Engineer"},
            headers=auth_headers,
        ).json()["access_token"]
        assert client.get(f"/api/work-daily/{rid}", headers={"Authorization": f"Bearer {token2}"}).status_code == 403

    def test_skill_bootstrap(self):
        from app.platform.database import SessionLocal
        from app.skill_hub.service import get_skill_by_name

        db = SessionLocal()
        try:
            skill = get_skill_by_name(db, WORK_DAILY_SKILL_NAME)
            assert skill is not None
            assert skill.display_name == "测试工程师日报解析"
        finally:
            db.close()
