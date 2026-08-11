"""企微日报/周报：风险快照对比与消息组装单测。"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.platform.database import SessionLocal
from app.test_manage.config import REPORT_KIND_DAILY
from app.test_manage.models import TmPushRun
from app.test_manage.push_report import (
    OpenRisk,
    ProgressSummary,
    build_daily_markdown,
    build_weekly_markdown,
    diff_risks,
    ensure_message_fits,
    utf8_len,
)
from app.test_manage import push_service
from app.test_manage.week import current_week_start, week_end, week_key


def _risk(aid: str, text: str = "阻塞") -> OpenRisk:
    return OpenRisk(
        action_id=aid,
        risk=text,
        task_title="Task",
        action_title=f"Act-{aid}",
        owner_name="hj",
        domain_name="平台",
        project_name="P",
        progress=50,
    )


def test_diff_added_unresolved_resolved():
    prev = {"a": _risk("a", "旧"), "b": _risk("b", "仍在")}
    cur = {"b": _risk("b", "仍在改文案"), "c": _risk("c", "新")}
    d = diff_risks(prev, cur)
    assert [x.action_id for x in d.added] == ["c"]
    assert [x.action_id for x in d.unresolved] == ["b"]
    assert d.resolved_ids == ["a"]


def test_daily_empty_still_returns_message():
    d = diff_risks({}, {})
    md = build_daily_markdown(today=date(2026, 7, 27), diff=d)
    assert md is not None
    assert "无开放风险" in md


def test_daily_contains_added_and_unresolved():
    d = diff_risks({"a": _risk("a")}, {"a": _risk("a"), "b": _risk("b", "新风险")})
    md = build_daily_markdown(today=date(2026, 7, 27), diff=d)
    assert md is not None
    assert "新增风险" in md
    assert "未解决" in md
    assert "新风险" in md
    assert 'color="#FF9200"' in md or "新风险" in md
    assert "新风险" in md


def test_weekly_always_has_progress():
    ws = current_week_start()
    summary = ProgressSummary(
        week_key=week_key(ws),
        week_start=ws,
        week_end=week_end(ws),
        task_count=3,
        action_count=5,
        progress_avg=66,
        risk_action_count=0,
        published_count=4,
        draft_count=1,
    )
    md = build_weekly_markdown(summary=summary, diff=diff_risks({}, {}))
    assert "【TPT测试周报】" in md
    assert "66%" in md
    assert "本周暂无 Task" in md or "暂无开放风险" in md
    assert "分领域" not in md
    assert "未解决" not in md
    assert 'color="#00B578"' in md or 'color="#FF9200"' in md


def test_weekly_task_risk_no_action_progress():
    """周报风险挂在 Task 下，并标明 Action 名。"""
    ws = current_week_start()
    summary = ProgressSummary(
        week_key=week_key(ws),
        week_start=ws,
        week_end=week_end(ws),
        task_count=1,
        action_count=2,
        progress_avg=50,
        risk_action_count=2,
        published_count=2,
        draft_count=0,
    )
    from app.test_manage.push_report import TaskProgressRow, TaskRiskItem

    rows = [
        TaskProgressRow(
            task_id="t1",
            task_title="大任务X",
            domain_name="Agent",
            project_name="P",
            progress_avg=50,
            action_count=2,
            published_count=2,
            done_count=0,
            draft_count=0,
            risk_count=2,
            risk_items=[
                TaskRiskItem(action_title="小项A", risk="阻塞A", owner_name="张三"),
                TaskRiskItem(action_title="小项B", risk="阻塞B", owner_name="李四"),
            ],
        )
    ]
    md = build_weekly_markdown(
        summary=summary, diff=diff_risks({}, {}), task_rows=rows
    )
    assert "大任务X" in md
    assert "小项A" in md
    assert "张三" in md
    assert "阻塞A" in md
    assert "小项B" in md
    assert "李四" in md
    assert "📊" not in md
    assert "2026-07-29T18" not in md
    assert "未解决" not in md


@pytest.mark.asyncio
async def test_ensure_message_fits_truncates_without_ai(monkeypatch):
    monkeypatch.setenv("MINIMAX_API_KEY", "")

    async def _boom(*_a, **_k):
        raise RuntimeError("no ai")

    monkeypatch.setattr(
        "app.ai_service.client.chat",
        _boom,
        raising=False,
    )
    long = "风险" * 5000
    out = await ensure_message_fits(long, max_bytes=200)
    assert utf8_len(out) <= 200
    assert "截断" in out


@pytest.mark.asyncio
async def test_daily_always_sends_even_without_risks(monkeypatch):
    """无开放风险也发日报（短进展 + 无风险文案）。"""
    day = date(2026, 7, 28)
    period = push_service.report.daily_period_key(day)

    with SessionLocal() as db:
        db.query(TmPushRun).filter(
            TmPushRun.report_kind == REPORT_KIND_DAILY,
            TmPushRun.period_key == period,
        ).delete(synchronize_session=False)
        db.commit()

    empty_summary = ProgressSummary(
        week_key="x",
        week_start=current_week_start(),
        week_end=week_end(current_week_start()),
        task_count=0,
        action_count=0,
        progress_avg=0,
        risk_action_count=0,
        published_count=0,
        draft_count=0,
        done_count=0,
    )
    monkeypatch.setattr(
        push_service.report,
        "collect_open_risks",
        lambda _db, week_start=None, week_key_s=None: {},
    )
    monkeypatch.setattr(
        push_service.report,
        "collect_progress_summary",
        lambda _db, week_start=None, week_key_s=None: empty_summary,
    )
    monkeypatch.setattr(
        push_service.report,
        "collect_today_action_lines",
        lambda _db, today=None, week_start=None, week_key_s=None: [],
    )
    monkeypatch.setattr(push_service.report, "load_snapshot_risks", lambda _db, _k: {})
    monkeypatch.setattr(push_service.report, "save_snapshot", lambda *a, **k: None)
    monkeypatch.setattr(
        push_service.report,
        "ensure_message_fits",
        AsyncMock(side_effect=lambda md, **_k: md),
    )
    sent = AsyncMock(return_value=None)
    monkeypatch.setattr(push_service, "send_markdown", sent)
    monkeypatch.setattr(push_service, "DINGTALK_WEBHOOK_URL", "https://oapi.dingtalk.com/robot/send?access_token=test")
    monkeypatch.setattr(push_service, "_require_webhook", lambda: None)

    with SessionLocal() as db:
        r1 = await push_service.push_daily(db, dry_run=False, force=False, today=day)
    assert r1.sent is True
    assert r1.skipped is False
    assert "无开放风险" in (r1.message or "")
    sent.assert_awaited_once()

    with SessionLocal() as db:
        r2 = await push_service.push_daily(db, dry_run=False, force=False, today=day)
    assert r2.skipped is True
    assert "已推送" in r2.reason


@pytest.mark.asyncio
async def test_push_requires_webhook(monkeypatch):
    cur = {"a": _risk("a")}
    empty_summary = ProgressSummary(
        week_key="x",
        week_start=current_week_start(),
        week_end=week_end(current_week_start()),
        task_count=0,
        action_count=0,
        progress_avg=0,
        risk_action_count=0,
        published_count=0,
        draft_count=0,
        done_count=0,
    )
    monkeypatch.setattr(
        push_service.report,
        "collect_open_risks",
        lambda _db, week_start=None, week_key_s=None: cur,
    )
    monkeypatch.setattr(
        push_service.report,
        "collect_progress_summary",
        lambda _db, week_start=None, week_key_s=None: empty_summary,
    )
    monkeypatch.setattr(
        push_service.report,
        "collect_today_action_lines",
        lambda _db, today=None, week_start=None, week_key_s=None: [],
    )
    monkeypatch.setattr(push_service.report, "load_snapshot_risks", lambda _db, _k: {})
    monkeypatch.setattr(
        push_service.report,
        "ensure_message_fits",
        AsyncMock(side_effect=lambda md, **_k: md),
    )
    monkeypatch.setattr(push_service, "DINGTALK_WEBHOOK_URL", "")

    with SessionLocal() as db:
        with pytest.raises(HTTPException) as ei:
            await push_service.push_daily(
                db, dry_run=False, force=True, today=date(2026, 7, 29)
            )
    assert ei.value.status_code == 400
