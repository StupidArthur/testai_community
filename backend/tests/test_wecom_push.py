"""钉钉日报/周报：阻塞快照对比与消息组装单测。"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.platform.database import SessionLocal
from app.test_manage.config import REPORT_KIND_DAILY
from app.test_manage.models import TmPushRun
from app.test_manage.push_report import (
    ActionProgressBuckets,
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


def test_daily_link_markdown_footer():
    from app.test_manage.push_report import build_daily_link_markdown

    md = build_daily_link_markdown(today=date(2026, 8, 12), screenshot_ok=True)
    assert "详情：" in md
    assert "/tm-screen" in md
    assert "view=today" in md
    assert "当前阻塞" not in md

    md2 = build_daily_link_markdown(today=date(2026, 8, 12), screenshot_ok=False)
    assert "截图未生成" in md2


def test_diff_added_unresolved_resolved():
    prev = {"a": _risk("a", "旧"), "b": _risk("b", "仍在")}
    cur = {"b": _risk("b", "仍在改文案"), "c": _risk("c", "新")}
    d = diff_risks(prev, cur)
    assert [x.action_id for x in d.added] == ["c"]
    assert [x.action_id for x in d.unresolved] == ["b"]
    assert d.resolved_ids == ["a"]


def test_daily_empty_still_returns_message():
    d = diff_risks({}, {})
    md = build_daily_markdown(
        today=date(2026, 7, 27),
        diff=d,
        buckets=ActionProgressBuckets(done=1, no_update_today=2),
    )
    assert md is not None
    assert "无开放阻塞" in md
    assert "Action 进度统计" in md
    assert "详情：" in md
    assert "今日 Action 进展" not in md


def test_daily_contains_blockers_and_buckets():
    d = diff_risks({"a": _risk("a")}, {"a": _risk("a"), "b": _risk("b", "环境不可用")})
    buckets = ActionProgressBuckets(
        done=1, no_update_today=3, progress_0_50=2, progress_50_100=4
    )
    summary = ProgressSummary(
        week_key="w",
        week_start=current_week_start(),
        week_end=week_end(current_week_start()),
        task_count=2,
        action_count=10,
        progress_avg=40,
        risk_action_count=2,
        published_count=9,
        draft_count=0,
        done_count=1,
    )
    md = build_daily_markdown(
        today=date(2026, 7, 27),
        diff=d,
        summary=summary,
        buckets=buckets,
        risk_layout="list",
    )
    assert "当前阻塞" in md
    assert "环境不可用" in md
    assert "Act-b" in md
    assert "hj" in md
    # 颜色辨识：正文近黑 / 阻塞橙；负责人灰（日报不展示域）
    assert 'color="#1677FF"' not in md
    assert 'color="#262626"' in md
    assert 'color="#FF9200"' in md
    assert "当前有阻塞" in md
    assert "无进度" in md
    assert "0–50%" in md
    assert "50–100%" in md
    assert "今日 Action 进展" not in md
    assert "详情：" in md
    assert "/tm-screen" in md
    assert "view=today" in md
    assert "1、" not in md
    # 阻塞条目不再展示 Action 进度%（底部四档文案「0–50%」仍可出现）
    assert ">50%</font>" not in md


@pytest.mark.asyncio
async def test_fit_daily_lists_all_blockers_no_omitted_hint(monkeypatch):
    """超长日报：开放阻塞全列，不出现「另有」；含进度统计。"""
    from app.test_manage import push_report as pr
    from app.test_manage.push_report import fit_daily_markdown

    monkeypatch.setattr(pr, "PUSH_AI_COMPRESS_ENABLED", False)

    cur = {
        f"r{i}": OpenRisk(
            action_id=f"r{i}",
            risk=f"环境不稳定间歇超时-{i}-" + ("详述" * 40),
            task_title=f"Task-{i // 4}",
            action_title=f"【压测】T-{i:02d}-长标题动作项",
            owner_name="管理员",
            domain_name=["平台", "Agent", "交付"][i % 3],
            project_name="P",
            progress=10 + i,
        )
        for i in range(22)
    }
    summary = ProgressSummary(
        week_key="w",
        week_start=current_week_start(),
        week_end=week_end(current_week_start()),
        task_count=5,
        action_count=30,
        progress_avg=30,
        risk_action_count=22,
        published_count=30,
        draft_count=0,
        done_count=0,
    )
    buckets = ActionProgressBuckets(
        done=2, no_update_today=10, progress_0_50=8, progress_50_100=10
    )
    md = await fit_daily_markdown(
        today=date(2026, 7, 27),
        diff=diff_risks({}, cur),
        summary=summary,
        buckets=buckets,
        max_bytes=4096,
    )
    assert "风险未列出" not in md
    assert "Action 未列出" not in md
    assert "当前阻塞" in md
    assert "Action 进度统计" in md
    assert utf8_len(md) <= 4096
    assert "1、" not in md
    assert "22、" not in md
    # 超长时可能隐藏 Action 名；日报不展示域，仍须近黑/阻塞橙与条目齐全
    assert 'color="#1677FF"' not in md
    assert 'color="#262626"' in md
    assert 'color="#FF9200"' in md
    # 极端超长时文字版可能硬截断；线上日报已改为「深链 + 截图」


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
        done_count=1,
    )
    md = build_weekly_markdown(summary=summary, diff=diff_risks({}, {}))
    assert "【TPT测试周报】" in md
    assert "66%" in md
    assert "本周结论" in md
    assert "完成" in md
    assert "1/5" in md
    assert "重点关注" in md
    assert "其余进行中的 Task" not in md
    assert "分领域" not in md
    assert "未解决" not in md
    assert "另有" not in md
    assert "已消除" not in md
    assert "阻塞 Task" in md
    assert "详情：" in md
    assert "/tm-screen" in md
    assert 'color="#262626"' in md or 'color="#8C8C8C"' in md


def test_weekly_focus_all_blocked_tasks():
    """周报重点关注列出全部阻塞 Task；无阻塞 Task / 其余进行中不进列表。"""
    ws = current_week_start()
    summary = ProgressSummary(
        week_key=week_key(ws),
        week_start=ws,
        week_end=week_end(ws),
        task_count=4,
        action_count=8,
        progress_avg=40,
        risk_action_count=6,
        published_count=8,
        draft_count=0,
        done_count=0,
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
            risk_count=3,
            lead_name="王负责",
            risk_items=[
                TaskRiskItem(action_title="小项A", risk="阻塞A", owner_name="张三"),
            ],
        ),
        TaskProgressRow(
            task_id="t2",
            task_title="任务Y",
            domain_name="平台",
            project_name="P",
            progress_avg=40,
            action_count=2,
            published_count=2,
            done_count=0,
            draft_count=0,
            risk_count=2,
            lead_name="李负责",
        ),
        TaskProgressRow(
            task_id="t3",
            task_title="任务Z",
            domain_name="交付",
            project_name="P",
            progress_avg=30,
            action_count=2,
            published_count=2,
            done_count=0,
            draft_count=0,
            risk_count=1,
            lead_name="赵负责",
        ),
        TaskProgressRow(
            task_id="t4",
            task_title="无阻塞任务",
            domain_name="平台",
            project_name="P",
            progress_avg=80,
            action_count=1,
            published_count=1,
            done_count=0,
            draft_count=0,
            risk_count=0,
            lead_name="钱负责",
        ),
    ]
    prev = {"a": _risk("a")}
    cur = {"a": _risk("a"), "b": _risk("b", "新阻塞")}
    md = build_weekly_markdown(
        summary=summary, diff=diff_risks(prev, cur), task_rows=rows
    )
    assert "本周结论" in md
    assert "重点关注" in md
    assert "大任务X" in md
    assert "任务Y" in md
    assert "任务Z" in md
    assert "无阻塞任务" not in md
    assert "其余进行中的 Task" not in md
    assert "完成 0/2" in md
    assert "阻塞 3" in md
    assert "小项A" not in md
    assert "阻塞A" not in md
    assert "另有" not in md
    assert "已消除" not in md
    assert "阻塞 Task" in md
    assert "详情：" in md
    assert "🗓️" not in md
    from app.test_manage.push_report import _fmt_week_span

    week_span = _fmt_week_span(ws, week_end(ws))
    assert week_span in md
    # 周区间跟在标题同行小字，不另起引用行
    assert f'size="1">{week_span}</font>' in md
    assert "> 🗓️" not in md
    assert "1、" not in md
    # KPI 数字加粗（与日报进度统计一致）
    assert "**" in md and "均进度" in md
    assert 'color="#262626"' in md
    assert 'color="#1677FF"' in md
    assert 'color="#FF9200"' in md


@pytest.mark.asyncio
async def test_fit_weekly_one_line_stays_short(monkeypatch):
    """重点关注周报通常很短；超长时也不出现「另有」。"""
    from app.test_manage import push_report as pr
    from app.test_manage.push_report import TaskProgressRow, fit_weekly_markdown

    monkeypatch.setattr(pr, "PUSH_AI_COMPRESS_ENABLED", False)

    ws = current_week_start()
    summary = ProgressSummary(
        week_key=week_key(ws),
        week_start=ws,
        week_end=week_end(ws),
        task_count=20,
        action_count=40,
        progress_avg=40,
        risk_action_count=10,
        published_count=40,
        draft_count=0,
        done_count=0,
    )
    rows = [
        TaskProgressRow(
            task_id=f"t{t}",
            task_title=f"长标题任务-{t}-" + ("X" * 20),
            domain_name="平台",
            project_name="P",
            progress_avg=10 + t,
            action_count=2,
            published_count=2,
            done_count=0,
            draft_count=0,
            risk_count=5 - (t % 5),
            lead_name="管理员",
        )
        for t in range(20)
    ]
    md = await fit_weekly_markdown(
        summary=summary,
        diff=diff_risks({}, {"a": _risk("a")}),
        task_rows=rows,
        max_bytes=4096,
    )
    assert utf8_len(md) <= 4096
    assert "另有" not in md
    assert "其余进行中的 Task" not in md
    assert "重点关注" in md


@pytest.mark.asyncio
async def test_daily_always_sends_even_without_risks(monkeypatch):
    day = date(2026, 8, 1)
    period = push_service.report.daily_period_key(day)
    db = SessionLocal()
    try:
        db.query(TmPushRun).filter(
            TmPushRun.report_kind == REPORT_KIND_DAILY,
            TmPushRun.period_key == period,
        ).delete()
        db.commit()
    finally:
        db.close()

    summary = ProgressSummary(
        week_key="w",
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
        lambda *a, **k: {},
    )
    monkeypatch.setattr(
        push_service.report,
        "collect_progress_summary",
        lambda *a, **k: summary,
    )
    monkeypatch.setattr(
        push_service.report,
        "collect_action_progress_buckets",
        lambda *a, **k: ActionProgressBuckets(),
    )
    monkeypatch.setattr(
        push_service.report,
        "load_snapshot_risks",
        lambda *a, **k: {},
    )
    monkeypatch.setattr(
        push_service.report,
        "save_snapshot",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(push_service, "_require_webhook", lambda: None)
    monkeypatch.setattr(
        push_service, "send_markdown", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        push_service, "send_image", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        push_service, "capture_today_screen_png", lambda **k: b"fake-png"
    )

    db = SessionLocal()
    try:
        r1 = await push_service.push_daily(db, dry_run=False, force=False, today=day)
        assert r1.sent is True
        assert r1.message and "详情：" in r1.message
        assert "/tm-screen" in r1.message
        assert "当前阻塞" not in r1.message

        r2 = await push_service.push_daily(db, dry_run=False, force=False, today=day)
        assert r2.skipped is True
    finally:
        db.close()


@pytest.mark.asyncio
async def test_daily_force_bypasses_idempotency(monkeypatch):
    day = date(2026, 8, 2)
    summary = ProgressSummary(
        week_key="w",
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
    monkeypatch.setattr(push_service.report, "collect_open_risks", lambda *a, **k: {})
    monkeypatch.setattr(
        push_service.report, "collect_progress_summary", lambda *a, **k: summary
    )
    monkeypatch.setattr(
        push_service.report,
        "collect_action_progress_buckets",
        lambda *a, **k: ActionProgressBuckets(),
    )
    monkeypatch.setattr(push_service.report, "load_snapshot_risks", lambda *a, **k: {})
    monkeypatch.setattr(push_service.report, "save_snapshot", lambda *a, **k: None)
    monkeypatch.setattr(push_service, "_require_webhook", lambda: None)
    monkeypatch.setattr(push_service, "send_markdown", AsyncMock(return_value=None))
    monkeypatch.setattr(push_service, "send_image", AsyncMock(return_value=None))
    monkeypatch.setattr(
        push_service, "capture_today_screen_png", lambda **k: b"fake-png"
    )
    monkeypatch.setattr(push_service, "_already_sent", lambda *a, **k: True)

    db = SessionLocal()
    try:
        r = await push_service.push_daily(
            db, dry_run=False, force=True, today=day
        )
        assert r.sent is True
    finally:
        db.close()


@pytest.mark.asyncio
async def test_ensure_message_fits_truncates():
    big = "测" * 5000
    out = await ensure_message_fits(big, max_bytes=100)
    assert utf8_len(out) <= 100
