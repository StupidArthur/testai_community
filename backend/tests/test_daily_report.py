"""工作日报 API 测试。"""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.ai_service.work_daily.models import WorkDailyAuditResult, WorkItem

MOCK_AUDIT = WorkDailyAuditResult(
    valid=True,
    work_items=[
        WorkItem(category="功能测试", description="开发日报模块", hours=6.0, ratio=1.0),
    ],
    total_hours=6.0,
    dimension_coverage=["功能测试"],
    summary="完成日报功能开发",
)


@pytest.fixture(autouse=True)
def _ensure_work_daily_skill(client):
    from app.daily_report.bootstrap import ensure_work_daily_skill

    ensure_work_daily_skill()


def _day(offset: int = 0) -> str:
    """相对今天的业务日（满足「最近 7 天可补交」）。"""
    return (date.today() - timedelta(days=offset)).isoformat()


def _payload(text: str = "今天做功能测试 6 小时。", *, days_ago: int = 0) -> dict:
    return {
        "report_date": _day(days_ago),
        "report_role": "测试工程师",
        "raw_text": text,
    }


class TestWorkDaily:
    def test_audit_endpoint(self, client, eng_headers):
        with patch(
            "app.ai_service.work_daily.audit.chat",
            new_callable=AsyncMock,
            return_value=MOCK_AUDIT.model_dump_json(),
        ):
            r = client.post("/api/work-daily/audit", json=_payload(), headers=eng_headers)
        assert r.status_code == 200, r.text
        assert r.json()["audit"]["valid"] is True

    def test_submit_and_list(self, client, eng_headers):
        with patch(
            "app.ai_service.work_daily.audit.chat",
            new_callable=AsyncMock,
            return_value=MOCK_AUDIT.model_dump_json(),
        ):
            r = client.post("/api/work-daily", json=_payload(), headers=eng_headers)
        assert r.status_code == 201
        body = r.json()
        assert body["audit"]["work_items"][0]["category"] == "功能测试"

        lst = client.get("/api/work-daily", headers=eng_headers)
        assert lst.status_code == 200
        assert len(lst.json()["items"]) >= 1

    def test_same_day_multiple_submits(self, client, eng_headers):
        day = _day(0)
        with patch(
            "app.ai_service.work_daily.audit.chat",
            new_callable=AsyncMock,
            return_value=MOCK_AUDIT.model_dump_json(),
        ):
            client.post("/api/work-daily", json=_payload("第一次"), headers=eng_headers)
            client.post("/api/work-daily", json=_payload("第二次"), headers=eng_headers)
        lst = client.get("/api/work-daily", headers=eng_headers)
        same_day = [x for x in lst.json()["items"] if x["report_date"] == day]
        assert len(same_day) >= 2

    def test_admin_can_read_engineer_report(self, client, auth_headers, eng_headers):
        with patch(
            "app.ai_service.work_daily.audit.chat",
            new_callable=AsyncMock,
            return_value=MOCK_AUDIT.model_dump_json(),
        ):
            created = client.post(
                "/api/work-daily",
                json=_payload(days_ago=1),
                headers=eng_headers,
            )
        assert created.status_code == 201, created.text
        report_id = created.json()["id"]

        assert client.get(f"/api/work-daily/{report_id}", headers=eng_headers).status_code == 200
        assert client.get(f"/api/work-daily/{report_id}", headers=auth_headers).status_code == 200

    def test_admin_export(self, client, auth_headers, eng_headers):
        day = _day(2)
        with patch(
            "app.ai_service.work_daily.audit.chat",
            new_callable=AsyncMock,
            return_value=MOCK_AUDIT.model_dump_json(),
        ):
            client.post(
                "/api/work-daily",
                json=_payload(days_ago=2),
                headers=eng_headers,
            )
        r = client.get("/api/work-daily/export", params={"report_date": day}, headers=auth_headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_list_pagination(self, client, eng_headers):
        page_date = _day(5)
        with patch(
            "app.ai_service.work_daily.audit.chat",
            new_callable=AsyncMock,
            return_value=MOCK_AUDIT.model_dump_json(),
        ):
            for i in range(12):
                client.post(
                    "/api/work-daily",
                    json={**_payload(days_ago=5), "raw_text": f"日报{i}"},
                    headers=eng_headers,
                )
        p1 = client.get(
            "/api/work-daily",
            params={"page": 1, "page_size": 10, "report_date": page_date},
            headers=eng_headers,
        )
        p2 = client.get(
            "/api/work-daily",
            params={"page": 2, "page_size": 10, "report_date": page_date},
            headers=eng_headers,
        )
        assert p1.json()["total"] >= 12
        assert len(p1.json()["items"]) == 10
        assert len(p2.json()["items"]) >= 2

    def test_reject_too_old_report_date(self, client, eng_headers):
        """超过补交窗口应 400。"""
        old = (date.today() - timedelta(days=30)).isoformat()
        with patch(
            "app.ai_service.work_daily.audit.chat",
            new_callable=AsyncMock,
            return_value=MOCK_AUDIT.model_dump_json(),
        ):
            r = client.post(
                "/api/work-daily/audit",
                json={**_payload(), "report_date": old},
                headers=eng_headers,
            )
        assert r.status_code == 400

    def test_format_dict_suggestions(self):
        from app.ai_service.work_daily.audit import _normalize

        result = _normalize({
            "valid": False,
            "validation_issues": [
                {"type": "time_mismatch", "severity": "warning", "detail": "工时差异 2 小时"},
            ],
            "suggestions": [
                {"type": "description_clarity", "severity": "minor", "detail": "建议简化描述"},
            ],
        })
        assert "time_mismatch" in result.validation_issues[0]
        assert "建议简化描述" in result.suggestions[0]
        assert "{" not in result.suggestions[0]
