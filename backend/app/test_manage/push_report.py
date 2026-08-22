"""
测试任务钉钉推送：开放阻塞采集、与上次快照对比、消息组装；日报偏 Action、周报偏 Task。
日报：当前阻塞列表 + Action 进度四档统计；单条 ≤4096。
周报：结论 + KPI + 重点关注（全部阻塞 Task，超长再截前几条）；超长则 AI 压整篇 / 硬截断。
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from typing import Any

from sqlalchemy.orm import Session, joinedload

from app.auth.models import User
from app.test_manage.config import (
    PUSH_AI_COMPRESS_ENABLED,
    PUSH_AI_COMPRESS_TARGET_BYTES,
    PUSH_AI_COMPRESS_TIMEOUT_SEC,
    PUSH_RISK_TEXT_MAX_CHARS,
    REPORT_KIND_DAILY,
    REPORT_KIND_WEEKLY,
    STATUS_CANCELLED,
    STATUS_DONE,
    STATUS_DRAFT,
    STATUS_PUBLISHED,
    WECOM_DAILY_ACTION_LINES_SOFT_MAX,
    WECOM_MSG_MAX_BYTES,
    WECOM_PUSH_RISK_ITEMS_SOFT_MAX,
    WECOM_RISK_TEXT_MAX_CHARS,
    WECOM_RISK_TITLE_MAX_CHARS,
    WECOM_WEEKLY_TASK_ROWS_SOFT_MAX,
    now_tm,
    resolve_board_detail_url,
)
from app.test_manage.models import TmAction, TmDomain, TmPushSnapshot, TmTask, TmWeekPeriod
from app.test_manage.service import _latest_progress
from app.test_manage.week import current_week_start, daily_context_week_start, week_end, week_key

log = logging.getLogger("app.test_manage.push")


def _report_footer() -> list[str]:
    """日/周报统一页脚：突出详情大屏链接（可点 + 明文 URL）。"""
    url = resolve_board_detail_url()
    return [
        "",
        "---",
        f"**详情大屏**：[点此打开今日大屏]({url})",
        _font("comment", url, size=_DINGTALK_FONT_SIZE_META),
    ]


def _resolve_report_week(
    db: Session,
    *,
    week_start: datetime | None = None,
    week_key_s: str | None = None,
) -> tuple[datetime, datetime, str]:
    """
    解析推送用周窗口。

    优先 week_key_s（与看板 tm_week_periods / Action.week_key 一致）；
    否则用 week_start 推导；再否则经典当前周。
    """
    if week_key_s:
        key = week_key_s
        row = db.query(TmWeekPeriod).filter(TmWeekPeriod.week_key == key).first()
        if row:
            return row.week_start, row.week_end, row.week_key
        ws = week_start or current_week_start()
        return ws, week_end(ws), key
    ws = week_start or daily_context_week_start()
    key = week_key(ws)
    row = db.query(TmWeekPeriod).filter(TmWeekPeriod.week_key == key).first()
    if row:
        return row.week_start, row.week_end, row.week_key
    return ws, week_end(ws), key


@dataclass
class OpenRisk:
    """单条开放风险（以 Action 为粒度；周报展示时再聚到 Task）。"""

    action_id: str
    risk: str
    task_title: str
    action_title: str
    owner_name: str
    domain_name: str
    project_name: str
    progress: int
    task_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "risk": self.risk,
            "task_title": self.task_title,
            "action_title": self.action_title,
            "owner_name": self.owner_name,
            "domain_name": self.domain_name,
            "project_name": self.project_name,
            "progress": self.progress,
            "task_id": self.task_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OpenRisk:
        return cls(
            action_id=str(data.get("action_id") or ""),
            risk=str(data.get("risk") or ""),
            task_title=str(data.get("task_title") or ""),
            action_title=str(data.get("action_title") or ""),
            owner_name=str(data.get("owner_name") or ""),
            domain_name=str(data.get("domain_name") or ""),
            project_name=str(data.get("project_name") or ""),
            progress=int(data.get("progress") or 0),
            task_id=str(data.get("task_id") or ""),
        )


@dataclass
class TaskRiskRow:
    """周报：Task 粒度风险行（不含 Action 名与进度）。"""

    task_id: str
    task_title: str
    domain_name: str
    risk_count: int
    risk_summary: str


@dataclass
class ProgressSummary:
    """周报用短进展。"""

    week_key: str
    week_start: datetime
    week_end: datetime
    task_count: int
    action_count: int
    progress_avg: int
    risk_action_count: int
    published_count: int
    draft_count: int
    done_count: int = 0


@dataclass
class ActionProgressBuckets:
    """
    日报底部 Action 进度分档（本周非草稿、非取消；互斥优先序）：
    已完成 → 今日未日更 → 0–50% → 50–100%。
    """

    done: int = 0
    no_update_today: int = 0
    progress_0_50: int = 0
    progress_50_100: int = 0

    @property
    def total(self) -> int:
        return (
            self.done
            + self.no_update_today
            + self.progress_0_50
            + self.progress_50_100
        )


@dataclass
class RiskDiff:
    """相对上次快照的增量。"""

    added: list[OpenRisk] = field(default_factory=list)
    unresolved: list[OpenRisk] = field(default_factory=list)
    resolved_ids: list[str] = field(default_factory=list)
    current: dict[str, OpenRisk] = field(default_factory=dict)


@dataclass
class TodayActionLine:
    """日报：今日有日更的 Action 行（按 Task 分组展示）。"""

    action_id: str
    task_id: str
    owner_name: str
    domain_name: str
    task_title: str
    action_title: str
    progress: int
    risk: str
    note: str
    status: str


@dataclass
class TaskRiskItem:
    """周报：挂在 Task 下的一条 Action 风险。"""

    action_title: str
    risk: str
    progress: int = 0
    owner_name: str = ""


@dataclass
class TaskProgressRow:
    """周报：Task 维度进度行（正文只展示摘要；risk_items 可选保留兼容）。"""

    task_id: str
    task_title: str
    domain_name: str
    project_name: str
    progress_avg: int
    action_count: int
    published_count: int
    done_count: int
    draft_count: int
    risk_count: int
    lead_name: str = ""
    risk_texts: list[str] = field(default_factory=list)
    risk_items: list[TaskRiskItem] = field(default_factory=list)


def _user_name_map(db: Session, user_ids: set[int]) -> dict[int, str]:
    """推送展示名：优先真实姓名，否则回退用户名。"""
    if not user_ids:
        return {}
    rows = db.query(User).filter(User.id.in_(user_ids)).all()
    out: dict[int, str] = {}
    for u in rows:
        name = (getattr(u, "real_name", None) or "").strip()
        out[u.id] = name or u.username
    return out


def collect_open_risks(
    db: Session,
    *,
    week_start: datetime | None = None,
    week_key_s: str | None = None,
) -> dict[str, OpenRisk]:
    """
    全项目：汇报周「进行中」Action 中，最新日更勾选「是否阻塞」的条目。

    优先 week_key_s（与看板活动周一致）；已完成 / 已取消 / 草稿不计入开放阻塞。
    """
    snap = collect_week_risk_snapshot(db, week_start=week_start, week_key_s=week_key_s)
    return {r.action_id: r for r in snap.blocking}


@dataclass
class WeekRiskSnapshot:
    """本周阻塞 + 风险（未勾阻塞）快照，供周报短说明。"""

    blocking: list[OpenRisk]
    risk_only: list[OpenRisk]

    @property
    def blocking_count(self) -> int:
        return len(self.blocking)

    @property
    def risk_only_count(self) -> int:
        return len(self.risk_only)

    @property
    def blocking_task_count(self) -> int:
        return len({r.task_id for r in self.blocking if r.task_id})

    @property
    def risk_count(self) -> int:
        """风险项 = 开放阻塞 + 有风险未勾阻塞（阻塞也算风险）。"""
        return self.blocking_count + self.risk_only_count

    @property
    def risk_task_count(self) -> int:
        """有任意风险文案（含阻塞）的 Task 数。"""
        ids = {r.task_id for r in self.blocking if r.task_id}
        ids |= {r.task_id for r in self.risk_only if r.task_id}
        return len(ids)


def collect_week_risk_snapshot(
    db: Session,
    *,
    week_start: datetime | None = None,
    week_key_s: str | None = None,
) -> WeekRiskSnapshot:
    """
    汇报周进行中 Action：拆成「开放阻塞」与「有风险未勾阻塞」。
    """
    _ws, _we, key = _resolve_report_week(db, week_start=week_start, week_key_s=week_key_s)
    actions = (
        db.query(TmAction)
        .options(
            joinedload(TmAction.daily_updates),
            joinedload(TmAction.task)
            .joinedload(TmTask.domain)
            .joinedload(TmDomain.project),
        )
        .filter(TmAction.week_key == key)
        .filter(TmAction.status == STATUS_PUBLISHED)
        .all()
    )
    owner_ids = {a.owner_id for a in actions}
    names = _user_name_map(db, owner_ids)
    blocking: list[OpenRisk] = []
    risk_only: list[OpenRisk] = []
    for a in actions:
        progress, risk, is_blocking = _latest_progress(a)
        risk = (risk or "").strip()
        if not risk:
            continue
        task = a.task
        domain = task.domain if task else None
        project = domain.project if domain else None
        item = OpenRisk(
            action_id=a.id,
            risk=risk,
            task_title=(task.title if task else "") or a.title,
            action_title=a.title,
            owner_name=names.get(a.owner_id, str(a.owner_id)),
            domain_name=(domain.name if domain else "") or "—",
            project_name=(project.name if project else "") or "—",
            progress=progress,
            task_id=a.task_id or "",
        )
        if is_blocking:
            blocking.append(item)
        else:
            risk_only.append(item)
    blocking.sort(key=lambda r: (-len((r.risk or "").strip()), r.task_title, r.action_title))
    risk_only.sort(key=lambda r: (-len((r.risk or "").strip()), r.task_title, r.action_title))
    return WeekRiskSnapshot(blocking=blocking, risk_only=risk_only)


def previous_week_key(db: Session, *, current_week_start: datetime) -> str | None:
    """取库内上一业务周的 week_key；无则 None。"""
    from app.test_manage.week import _as_local

    ws = _as_local(current_week_start)
    prev = (
        db.query(TmWeekPeriod)
        .filter(TmWeekPeriod.week_end <= ws)
        .order_by(TmWeekPeriod.week_end.desc())
        .first()
    )
    return prev.week_key if prev else None


def compute_matched_task_progress_delta(
    db: Session,
    *,
    this_week_key: str,
    last_week_key: str | None,
) -> tuple[int | None, int]:
    """
    跨周可比 Task 的进度变化均值。

    口径：本周有 Action 的 Task 里，仅取「上周也有 Action」的 Task；
    每个 Task 用该周展示进度（手填优先，否则 Action 平均）做差：本周 − 上周；
    再对差值取算术平均并四舍五入为整数。
    上周没有的本周 Task 不计入。

    例：两 Task 本周 10%/50%、上周 2%/40% → 差值 8%/10% → 均值 9%。

    返回 (平均差值, 可比 Task 数)；无可比 Task 时平均差值为 None。
    """
    if not last_week_key:
        return None, 0
    this_rows = collect_task_progress_rows(db, week_key_s=this_week_key)
    last_rows = collect_task_progress_rows(db, week_key_s=last_week_key)
    last_by_id = {r.task_id: r.progress_avg for r in last_rows}
    deltas: list[int] = []
    for row in this_rows:
        if row.task_id not in last_by_id:
            continue
        deltas.append(int(row.progress_avg) - int(last_by_id[row.task_id]))
    if not deltas:
        return None, 0
    avg = int(round(sum(deltas) / len(deltas)))
    return avg, len(deltas)


def format_matched_progress_delta(avg_delta: int | None, *, matched_n: int = 0) -> str:
    """
    跨周可比 Task 进度差均值的展示文案（周报 KPI 行，加粗 + 大号着色）。

    matched_n 仅供调用方统计，文案不展示个数。
    """
    _ = matched_n
    label = _font("text", "平均进度较上周", size=_DINGTALK_FONT_SIZE_TITLE)
    if avg_delta is None:
        return (
            f"**{label}** "
            f"{_font('comment', '—（无跨周可比 Task）', size=_DINGTALK_FONT_SIZE_TITLE)}"
        )
    if avg_delta > 0:
        return (
            f"**{label}** "
            f"**{_font('info', f'↑ 增加 {avg_delta}%', size=_DINGTALK_FONT_SIZE_TITLE)}**"
        )
    if avg_delta < 0:
        return (
            f"**{label}** "
            f"**{_font('warning', f'↓ 减少 {abs(avg_delta)}%', size=_DINGTALK_FONT_SIZE_TITLE)}**"
        )
    return (
        f"**{label}** "
        f"**{_font('comment', '持平 0%', size=_DINGTALK_FONT_SIZE_TITLE)}**"
    )


def build_weekly_brief_text(
    snap: WeekRiskSnapshot,
    *,
    progress_delta: int | None,
    matched_task_count: int = 0,
) -> str:
    """
    周报短说明（无明细列表）：两行汇总 + 截图引导。

    钉钉 sampleMarkdown 会折叠普通换行，故用「空行 + 列表项」强制分行：
    第 1 项：开放阻塞 / 风险（含阻塞）— 加粗大号 + 数字着色
    第 2 项：跨周可比 Task 进度差均值 — 同上
    引导句：独立段落（先 <br> 打断列表），不加粗、不进列表；灰色略小字
    """
    progress_bit = format_matched_progress_delta(
        progress_delta, matched_n=matched_task_count
    )
    sz = _DINGTALK_FONT_SIZE_TITLE
    row1 = (
        f"**{_font('danger', '开放阻塞', size=sz)}** "
        f"**{_font('warning', f'{snap.blocking_count} 项', size=sz)}**"
        f"{_font('text', '（涉及 Task ', size=sz)}"
        f"**{_font('warning', str(snap.blocking_task_count), size=sz)}**"
        f"{_font('text', '）', size=sz)}"
        "　"
        f"**{_font('warning', '风险', size=sz)}** "
        f"**{_font('warning', f'{snap.risk_count} 项', size=sz)}**"
        f"{_font('text', '（涉及 Task ', size=sz)}"
        f"**{_font('warning', str(snap.risk_task_count), size=sz)}**"
        f"{_font('text', '）', size=sz)}"
    )
    # 引导句：不加粗、不进列表；灰色 + 略小字号。
    # 钉钉会把紧跟列表的段落吞成第 3 条，故用 <br> 打断列表后再写 hint。
    hint = _font(
        "comment",
        "本周大屏 Task 明细见下图；完整交互请点详情链接打开大屏。",
        size=_DINGTALK_FONT_SIZE_BODY,
    )
    # 列表项 + 空行：钉钉端才会稳定分成两行（勿依赖纯 \\n / 单独 <br>）
    return "\n".join(
        [
            f"- {row1}",
            "",
            f"- {progress_bit}",
            "",
            "<br>",
            hint,
        ]
    ).strip()


def collect_progress_summary(
    db: Session,
    *,
    week_start: datetime | None = None,
    week_key_s: str | None = None,
) -> ProgressSummary:
    """全项目本周短进展（与看板 summary 口径一致）。"""
    ws, we, key = _resolve_report_week(db, week_start=week_start, week_key_s=week_key_s)
    actions = (
        db.query(TmAction)
        .options(joinedload(TmAction.daily_updates))
        .filter(TmAction.week_key == key)
        .filter(TmAction.status != STATUS_CANCELLED)
        .all()
    )
    task_ids = {a.task_id for a in actions}
    progresses: list[int] = []
    risk_n = 0
    published = 0
    draft = 0
    done = 0
    for a in actions:
        p, risk, is_blocking = _latest_progress(a)
        progresses.append(p)
        if a.status == "published" and (risk or "").strip() and is_blocking:
            risk_n += 1
        if a.status == "published":
            published += 1
        elif a.status == "draft":
            draft += 1
        elif a.status == "done":
            done += 1
    avg = int(round(sum(progresses) / len(progresses))) if progresses else 0
    return ProgressSummary(
        week_key=key,
        week_start=ws,
        week_end=we,
        task_count=len(task_ids),
        action_count=len(actions),
        progress_avg=avg,
        risk_action_count=risk_n,
        published_count=published,
        draft_count=draft,
        done_count=done,
    )


def collect_action_progress_buckets(
    db: Session,
    *,
    today: date,
    week_start: datetime | None = None,
    week_key_s: str | None = None,
) -> ActionProgressBuckets:
    """
    本周非草稿 Action 四档统计。
    无进度 = 未完成且今日尚未提交日更。
    """
    _ws, _we, key = _resolve_report_week(db, week_start=week_start, week_key_s=week_key_s)
    actions = (
        db.query(TmAction)
        .options(joinedload(TmAction.daily_updates))
        .filter(TmAction.week_key == key)
        .filter(TmAction.status != STATUS_CANCELLED)
        .filter(TmAction.status != STATUS_DRAFT)
        .all()
    )
    buckets = ActionProgressBuckets()
    for a in actions:
        if a.status == STATUS_DONE:
            buckets.done += 1
            continue
        has_today = any(
            (row.report_date == today) for row in (a.daily_updates or [])
        )
        if not has_today:
            buckets.no_update_today += 1
            continue
        p, _risk, _blk = _latest_progress(a)
        if p < 50:
            buckets.progress_0_50 += 1
        else:
            buckets.progress_50_100 += 1
    return buckets


def collect_today_action_lines(
    db: Session,
    *,
    today: date,
    week_start: datetime | None = None,
    week_key_s: str | None = None,
) -> list[TodayActionLine]:
    """
    日报专用：汇报周内、今日有日更的 Action（Action 粒度）。
    排序：领域 → Task 标题 → 有风险优先 → 进度升序 → Action 标题（展示时按 Task 分组）。
    """
    _ws, _we, key = _resolve_report_week(db, week_start=week_start, week_key_s=week_key_s)
    actions = (
        db.query(TmAction)
        .options(
            joinedload(TmAction.daily_updates),
            joinedload(TmAction.task)
            .joinedload(TmTask.domain)
            .joinedload(TmDomain.project),
        )
        .filter(TmAction.week_key == key)
        .filter(TmAction.status != STATUS_CANCELLED)
        .all()
    )
    names = _user_name_map(db, {a.owner_id for a in actions})
    lines: list[TodayActionLine] = []
    for a in actions:
        du = None
        for row in a.daily_updates or []:
            if row.report_date == today:
                du = row
                break
        if du is None:
            continue
        task = a.task
        domain = task.domain if task else None
        risk = (du.risk_blocker or "").strip()
        lines.append(
            TodayActionLine(
                action_id=a.id,
                task_id=(task.id if task else "") or a.task_id or "",
                owner_name=names.get(a.owner_id, str(a.owner_id)),
                domain_name=(domain.name if domain else "") or "—",
                task_title=(task.title if task else "") or "",
                action_title=a.title,
                progress=int(du.progress_percent or 0),
                risk=risk,
                note=(du.progress_note or "").strip(),
                status=a.status,
            )
        )
    lines.sort(
        key=lambda x: (
            x.domain_name,
            x.task_title,
            x.task_id,
            0 if x.risk else 1,
            x.progress,
            x.action_title,
        )
    )
    return lines


def collect_task_progress_rows(
    db: Session,
    *,
    week_start: datetime | None = None,
    week_key_s: str | None = None,
) -> list[TaskProgressRow]:
    """周报专用：本周有 Action 的 Task 汇总（Task 粒度）。"""
    _ws, _we, key = _resolve_report_week(db, week_start=week_start, week_key_s=week_key_s)
    actions = (
        db.query(TmAction)
        .options(
            joinedload(TmAction.daily_updates),
            joinedload(TmAction.task)
            .joinedload(TmTask.domain)
            .joinedload(TmDomain.project),
        )
        .filter(TmAction.week_key == key)
        .filter(TmAction.status != STATUS_CANCELLED)
        .all()
    )
    by_task: dict[str, list[TmAction]] = {}
    for a in actions:
        by_task.setdefault(a.task_id, []).append(a)

    owner_ids = {a.owner_id for a in actions}
    lead_ids = {a.task.lead_id for a in actions if a.task is not None}
    names = _user_name_map(db, owner_ids | lead_ids)

    rows: list[TaskProgressRow] = []
    for tid, acts in by_task.items():
        task = acts[0].task
        domain = task.domain if task else None
        project = domain.project if domain else None
        progresses: list[int] = []
        risk_n = published = done = draft = 0
        risk_texts: list[str] = []
        risk_items: list[TaskRiskItem] = []
        seen_risk: set[str] = set()
        for a in acts:
            p, risk, is_blocking = _latest_progress(a)
            progresses.append(p)
            risk = (risk or "").strip()
            if a.status == STATUS_PUBLISHED and risk and is_blocking:
                risk_n += 1
                risk_items.append(
                    TaskRiskItem(
                        action_title=a.title or "",
                        risk=risk,
                        progress=p,
                        owner_name=names.get(a.owner_id, str(a.owner_id)),
                    )
                )
                if risk not in seen_risk:
                    seen_risk.add(risk)
                    risk_texts.append(risk)
            if a.status == STATUS_PUBLISHED:
                published += 1
            elif a.status == STATUS_DONE:
                done += 1
            elif a.status == STATUS_DRAFT:
                draft += 1
        avg = int(round(sum(progresses) / len(progresses))) if progresses else 0
        from app.test_manage.models import TmTaskWeekProgress

        manual = (
            db.query(TmTaskWeekProgress)
            .filter(
                TmTaskWeekProgress.task_id == tid,
                TmTaskWeekProgress.week_key == key,
            )
            .first()
        )
        display = int(manual.progress_percent) if manual else avg
        lead_id = task.lead_id if task else None
        lead_name = names.get(lead_id, "") if lead_id is not None else ""
        rows.append(
            TaskProgressRow(
                task_id=tid,
                task_title=(task.title if task else tid) or tid,
                domain_name=(domain.name if domain else "") or "—",
                project_name=(project.name if project else "") or "—",
                progress_avg=display,
                action_count=len(acts),
                published_count=published,
                done_count=done,
                draft_count=draft,
                risk_count=risk_n,
                lead_name=lead_name,
                risk_texts=risk_texts,
                risk_items=risk_items,
            )
        )
    # 风险数高→低，再按均进度低→高（落后在前）
    rows.sort(
        key=lambda r: (-r.risk_count, r.progress_avg, r.domain_name, r.task_title)
    )
    return rows


def load_snapshot_risks(db: Session, report_kind: str) -> dict[str, OpenRisk]:
    row = (
        db.query(TmPushSnapshot)
        .filter(TmPushSnapshot.report_kind == report_kind)
        .first()
    )
    if not row or not (row.open_risks_json or "").strip():
        return {}
    try:
        raw = json.loads(row.open_risks_json)
    except json.JSONDecodeError:
        log.warning("invalid push snapshot json for %s", report_kind)
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, OpenRisk] = {}
    for aid, item in raw.items():
        if isinstance(item, dict):
            out[str(aid)] = OpenRisk.from_dict({**item, "action_id": aid})
    return out


def save_snapshot(
    db: Session,
    *,
    report_kind: str,
    current: dict[str, OpenRisk],
    period_key: str,
    message: str | None,
    trigger: str,
) -> None:
    payload = {aid: r.to_dict() for aid, r in current.items()}
    row = (
        db.query(TmPushSnapshot)
        .filter(TmPushSnapshot.report_kind == report_kind)
        .first()
    )
    if row is None:
        row = TmPushSnapshot(report_kind=report_kind)
        db.add(row)
    row.open_risks_json = json.dumps(payload, ensure_ascii=False)
    row.last_period_key = period_key
    row.last_message = message
    row.last_trigger = trigger
    db.commit()


def diff_risks(
    previous: dict[str, OpenRisk], current: dict[str, OpenRisk]
) -> RiskDiff:
    """新增 = 本次有上次无；未解决 = 两边都有；已解决 = 上次有本次无。"""
    added = [current[k] for k in current if k not in previous]
    unresolved = [current[k] for k in current if k in previous]
    resolved_ids = [k for k in previous if k not in current]
    # 稳定排序：领域 → Task → Action
    key_fn = lambda r: (r.domain_name, r.task_title, r.action_title, r.action_id)
    added.sort(key=key_fn)
    unresolved.sort(key=key_fn)
    return RiskDiff(
        added=added,
        unresolved=unresolved,
        resolved_ids=resolved_ids,
        current=current,
    )


def _fmt_dt(dt: datetime) -> str:
    return dt.strftime("%m-%d %H:%M")


def _fmt_day(d: date | datetime) -> str:
    if isinstance(d, datetime):
        return d.strftime("%m-%d")
    return d.strftime("%m-%d")


def daily_report_heading(today: date) -> str:
    """日报钉钉标题 / 正文首行：【TPT测试日报-MM-DD】。"""
    return f"【TPT测试日报-{_fmt_day(today)}】"


def weekly_report_heading() -> str:
    """周报钉钉标题 / 正文首行：【TPT测试周报】。"""
    return "【TPT测试周报】"


# 钉钉 markdown 着色（对齐企微 info=绿 / comment=灰 / warning=橙）
# 色号须用双引号，PC 与手机端才都能显示颜色
_DINGTALK_FONT_COLORS = {
    "info": "#00B578",
    "comment": "#8C8C8C",
    "warning": "#FF9200",
    # 阻塞标题感叹号：真红（区别于 warning 橙）
    "danger": "#FF4D4F",
    # 领域标签：蓝，与进度绿 / 风险橙区分
    "domain": "#1677FF",
    # 周报主文案：近黑，避免大面积绿色
    "text": "#262626",
}

# 钉钉 <font size>：标题略大、明细略小，拉开层次（1 小 … 7 大）
_DINGTALK_FONT_SIZE_TITLE = 4
_DINGTALK_FONT_SIZE_META = 1
_DINGTALK_FONT_SIZE_BODY = 2

# 阻塞/重点关注标题：钉钉 emoji 易变黑白，用着色双叹号加厚视觉
_DINGTALK_BLOCKER_MARK = "！！"
_DINGTALK_BLOCKER_MARK_COLOR = "danger"
# 周报「本周结论」行首标记（标题不再放 clipboard emoji）
_DINGTALK_WEEKLY_CONCLUSION_MARK = "📋"


def _blocker_section_title(label: str = "当前阻塞") -> str:
    """日/周报警示区标题：红色双叹号 + 文案。"""
    return f"**{_font(_DINGTALK_BLOCKER_MARK_COLOR, _DINGTALK_BLOCKER_MARK)} {label}**"


def _font(color: str, text: str, *, size: int | None = None) -> str:
    """钉钉 font 着色；可选 size 拉开标题 / 明细层次。"""
    hex_color = _DINGTALK_FONT_COLORS.get(color, _DINGTALK_FONT_COLORS["comment"])
    if size is None:
        return f'<font color="{hex_color}">{text or ""}</font>'
    return f'<font color="{hex_color}" size="{int(size)}">{text or ""}</font>'


def _progress_tone(percent: int) -> str:
    """
    日/周报进度着色：默认近黑；仅落后(<50)用橙提示。
    不用绿/灰跳色，避免列表「花花绿绿」无层次。
    """
    if percent < 50:
        return "warning"
    return "text"


def _weekly_progress_tone(percent: int) -> str:
    """周报进度着色（与日报同一口径）。"""
    return _progress_tone(percent)


def _dingtalk_index(n: int) -> str:
    """
    钉钉 markdown 会把「1. / 2.」当成有序列表，常把整段都显示成末项序号（如全变成 22.）。
    用顿号「1、」避免被解析为 ordered list。
    """
    return f"{n}、"


def _status_tag(status: str) -> str:
    if status == STATUS_DONE:
        return "完成"
    if status == STATUS_DRAFT:
        return "草稿"
    return "进行中"


def _clip(text: str, max_chars: int) -> str:
    """标题等短字段截断（带省略号）。说明/风险正文请用 _full_or_summary，避免半句截断。"""
    s = (text or "").replace("\n", " ").strip()
    if len(s) <= max_chars:
        return s
    if max_chars <= 1:
        return "…"
    return s[: max_chars - 1] + "…"


def _full_or_summary(text: str, max_chars: int) -> str:
    """
    说明/风险展示：不超过上限则全文；超过则不做半句「…」截断，
    交由上层先 AI 总结。此处若仍超长，只取完整到标点的前缀（无省略号）。
    max_chars<=0 表示不展示。
    """
    s = (text or "").replace("\n", " ").strip()
    if max_chars <= 0 or not s:
        return ""
    if len(s) <= max_chars:
        return s
    # 尽量在句号/分号/问叹号处收束；不用逗号作「带标点结尾」，避免「超时，」半句
    cut = s[:max_chars]
    for sep in ("。", "；", "!", "？", "?", ";"):
        pos = cut.rfind(sep)
        if pos >= max(8, max_chars // 3):
            return cut[: pos + 1].strip()
    # 弱收束：在逗号前截成完整分句（不保留逗号），避免「疑下游限」半词
    for sep in ("，", ",", "、"):
        pos = cut.rfind(sep)
        if pos >= max(8, max_chars // 3):
            return cut[:pos].strip()
    soft = cut.rstrip("，,、；;：: ").strip()
    if len(soft) >= max(8, max_chars // 2):
        return soft
    return ""


def _brief_text(text: str, max_chars: int) -> str:
    """
    截断前先剥掉「【风险压测-N】」等无信息前缀；正文用 _full_or_summary（不打 …）。
    """
    s = (text or "").replace("\n", " ").strip()
    while True:
        m = re.match(r"【[^】]{0,40}】\s*", s)
        if not m:
            break
        tag = m.group(0)
        if any(k in tag for k in ("压测", "风险压测", "说明压测")):
            s = s[m.end() :].strip()
            continue
        break
    s = re.sub(r"^(?:阻塞|风险)\s*[：:]\s*", "", s).strip() or (text or "").strip()
    return _full_or_summary(s, max_chars)


def _format_daily_action_section(
    lines: list[TodayActionLine],
    *,
    max_lines: int,
    note_max: int = 48,
    risk_max: int = 48,
    ultra_compact: bool = False,
    include_risk: bool = True,
) -> tuple[list[str], int]:
    """
    按 Task 分组的今日 Action 进展；返回 (正文行, 省略数)。

    ultra_compact：风险/说明并入 Action 行以省字节；Task 组之间仍保留空行（钉钉不粘连）。
    note_max 较小时自动 lean：去掉负责人/状态文案，保留颜色层次与说明/风险。
    include_risk：False 时不在 Action 下重复写风险（风险区已在上方展开时用）。
    """
    if max_lines <= 0:
        if not lines:
            return ([_font("comment", "今日暂无 Action 日更提交"), ""], 0)
        return ([_font("comment", "今日 Action 明细已省略")], len(lines))
    shown = lines[:max_lines]
    omitted = max(0, len(lines) - len(shown))
    parts: list[str] = ["**📌 今日 Action 进展（按 Task）**", ""]
    if not shown:
        parts.append(_font("comment", "今日暂无 Action 日更提交"))
        parts.append("")
        return parts, 0

    lean = note_max <= 16 or ultra_compact
    cur_task_id: str | None = None
    for row in shown:
        if row.task_id != cur_task_id:
            if cur_task_id is not None:
                parts.append("")
            cur_task_id = row.task_id
            task_label = _clip(row.task_title, 32 if lean else 48) or "（无标题 Task）"
            domain = (row.domain_name or "—").strip() or "—"
            # Task 行加粗作分区锚点；下方 Action 不加粗，靠层级辨识
            parts.append(f"{_font('domain', f'【{domain}】')} **Task：{task_label}**")
        prog = _font(_progress_tone(row.progress), f"{row.progress}%")
        title_max = 26 if lean else 40
        action_title = _font("text", _clip(row.action_title, title_max))
        if lean:
            line = f"- {action_title} {prog}"
        else:
            owner = (row.owner_name or "").strip()
            owner_bit = f" · {_font('comment', owner)}" if owner else ""
            status = _status_tag(row.status)
            line = (
                f"- {action_title}{owner_bit}　"
                f"{_font('comment', status)} {prog}"
            )
        show_risk = include_risk and bool(row.risk) and risk_max > 0
        if ultra_compact:
            if show_risk:
                line += f"　{_font('comment', f'⚠{_brief_text(row.risk, risk_max)}')}"
            if row.note and note_max > 0:
                line += f"　{_font('comment', _brief_text(row.note, note_max))}"
            parts.append(line)
        else:
            parts.append(line)
            if show_risk:
                parts.append(
                    f"> {_font('comment', f'⚠ {_brief_text(row.risk, risk_max)}')}"
                )
            if row.note and note_max > 0:
                parts.append(
                    f"> {_font('comment', f'说明：{_brief_text(row.note, note_max)}')}"
                )
    parts.append("")
    return parts, omitted


def _blocker_fields(r: OpenRisk, *, text_max: int, action_max: int, task_max: int) -> tuple[str, str, str, str]:
    """抽出域 / Task / Action / 阻塞四个展示字段。"""
    domain = (r.domain_name or "—").strip() or "—"
    task = _clip((r.task_title or "").strip() or "（无标题 Task）", task_max)
    action = _clip((r.action_title or "").strip() or "（无标题 Action）", action_max)
    blocker = _brief_text(r.risk, text_max) or "（未填写阻塞说明）"
    return domain, task, action, blocker


def _format_blocker_item(
    r: OpenRisk,
    *,
    index: int = 0,
    text_max: int,
    action_max: int,
    task_max: int,
    multiline: bool,
    show_action: bool = True,
    show_progress: bool = False,
    show_owner: bool = True,
    show_domain: bool = True,
    show_index: bool = False,
) -> str:
    """
    日报阻塞条目：标题略大、明细略小；颜色分层。
    - 域标签：蓝 + 标题字号（日报默认关）
    - Task：【】框 + 近黑加粗略大；Action：普通小字（不加粗）
    - 负责人灰；默认不展示进度%
    - 阻塞正文：橙 + 正文字号
    - 默认无序号（钉钉有序列表易错位）
    """
    del index  # 保留调用方传参兼容；正文默认不展示序号
    domain, task, action, blocker = _blocker_fields(
        r, text_max=text_max, action_max=action_max, task_max=task_max
    )
    owner = (r.owner_name or "").strip()
    owner_bit = (
        f" · {_font('comment', owner, size=_DINGTALK_FONT_SIZE_META)}"
        if show_owner and owner
        else ""
    )
    prog = (
        _font(_progress_tone(r.progress), f"{r.progress}%", size=_DINGTALK_FONT_SIZE_META)
        if show_progress
        else ""
    )
    domain_bit = (
        f"{_font('domain', f'[{domain}]', size=_DINGTALK_FONT_SIZE_TITLE)} "
        if show_domain
        else ""
    )
    # show_index 保留扩展位；当前产品默认关闭，避免「1、2、」占位
    _ = show_index
    # A+B：Task【】框 + 加粗；标题已含【（如【UI】…）则不再外套一层
    task_disp = task if "【" in task else f"【{task}】"
    task_title = f"**{_font('text', task_disp, size=_DINGTALK_FONT_SIZE_TITLE)}**"
    head = f"- {domain_bit}{task_title}"
    # 无 Action 时负责人挂 Task；有 Action 时挂 Action，避免重复
    if owner_bit and not show_action:
        head = f"{head}{owner_bit}"
    action_owner = owner_bit if show_action else ""
    action_bit = (
        f" · {_font('text', action, size=_DINGTALK_FONT_SIZE_META)}"
        if show_action and action
        else ""
    )
    blocker_bit = _font("warning", blocker, size=_DINGTALK_FONT_SIZE_BODY)
    if multiline:
        if show_action:
            mid = (
                f"  {_font('text', action, size=_DINGTALK_FONT_SIZE_META)}"
                f"{action_owner} {prog}"
            ).rstrip()
        else:
            mid = f"  {prog}" if prog else ""
        lines = [head]
        if mid:
            lines.append(mid)
        lines.extend([f"  {blocker_bit}", ""])
        return "\n".join(lines)
    # 单行紧凑：【Task】 · Action · 阻塞
    mid = (
        f"{action_bit}{action_owner}  {prog}".rstrip()
        if (action_bit or action_owner or prog)
        else ""
    )
    if mid:
        return f"{head}{mid} · {blocker_bit}"
    return f"{head} · {blocker_bit}"


def _risk_block(
    r: OpenRisk, *, index: int, tone: str = "warning", text_max: int | None = None
) -> str:
    """日报阻塞块：多行彩色分层（空间够时）；不展示域。"""
    del tone
    max_t = WECOM_RISK_TEXT_MAX_CHARS if text_max is None else text_max
    return _format_blocker_item(
        r,
        index=index,
        text_max=max_t,
        action_max=WECOM_RISK_TITLE_MAX_CHARS,
        task_max=28,
        multiline=True,
        show_action=True,
        show_progress=False,
        show_owner=True,
        show_domain=False,
    )


def _risk_line_compact(
    r: OpenRisk, *, index: int, tone: str = "warning", text_max: int = 22
) -> str:
    """单行彩色：Task黑 / Action 普通字重 / 负责人灰 / 阻塞橙；不展示域与进度%。"""
    del tone
    return _format_blocker_item(
        r,
        index=index,
        text_max=text_max,
        action_max=22,
        task_max=20,
        multiline=False,
        show_action=True,
        show_progress=False,
        show_owner=True,
        show_domain=False,
    )


def _risk_line_plain(
    r: OpenRisk, *, index: int, text_max: int = 12, title_max: int = 18
) -> str:
    """
    极限省字节：单行着色；去掉域与进度；优先保留 Action 名（带 Action：标签）。
    title_max 很低时才藏 Action / 负责人。
    """
    return _format_blocker_item(
        r,
        index=index,
        text_max=text_max,
        action_max=title_max,
        task_max=max(6, title_max),
        multiline=False,
        show_action=title_max >= 6,
        show_progress=False,
        # 先藏负责人，尽量保留 Action：名称
        show_owner=title_max >= 12,
        show_domain=False,
    )



def _task_risk_block(r: OpenRisk, *, index: int, tone: str = "warning") -> str:
    """兼容旧调用：周报已改用 TaskRiskRow。"""
    return _weekly_task_risk_block(
        TaskRiskRow(
            task_id="",
            task_title=r.task_title,
            domain_name=r.domain_name,
            risk_count=1,
            risk_summary=r.risk,
        ),
        index=index,
    )


def _weekly_task_risk_block(row: TaskRiskRow, *, index: int) -> str:
    """周报风险：仅 Task + 风险摘要，不写 Action、不写进度。"""
    title = _clip(row.task_title, WECOM_RISK_TITLE_MAX_CHARS)
    risk = _clip(row.risk_summary, WECOM_RISK_TEXT_MAX_CHARS)
    return "\n".join(
        [
            f"> **{_dingtalk_index(index)}** {_font('warning', f'[{row.domain_name}] {title}')}"
            f"　{_font('warning', f'阻塞×{row.risk_count}')}",
            f"> {_font('warning', risk)}",
        ]
    )


def aggregate_open_risks_by_task(current: dict[str, OpenRisk]) -> list[TaskRiskRow]:
    """
    将 Action 开放阻塞聚合成 Task 行（周报用）。
    按 risk_count 降序；同一 Task 下多条阻塞文案用分号拼接去重。
    """
    buckets: dict[str, list[OpenRisk]] = {}
    for r in current.values():
        tid = (r.task_id or "").strip() or f"title:{r.task_title}|{r.domain_name}"
        buckets.setdefault(tid, []).append(r)

    rows: list[TaskRiskRow] = []
    for tid, items in buckets.items():
        texts: list[str] = []
        seen: set[str] = set()
        for it in items:
            t = (it.risk or "").strip()
            if t and t not in seen:
                seen.add(t)
                texts.append(t)
        sample = items[0]
        rows.append(
            TaskRiskRow(
                task_id=tid,
                task_title=sample.task_title,
                domain_name=sample.domain_name,
                risk_count=len(items),
                risk_summary="；".join(texts) if texts else "（有阻塞）",
            )
        )
    rows.sort(key=lambda r: (-r.risk_count, r.domain_name, r.task_title))
    return rows


def _pick_task_risks_for_message(
    rows: list[TaskRiskRow], *, max_items: int
) -> tuple[list[TaskRiskRow], int]:
    if max_items <= 0:
        return [], len(rows)
    shown = rows[:max_items]
    return shown, max(0, len(rows) - len(shown))


def _pick_risks_for_message(
    added: list[OpenRisk],
    unresolved: list[OpenRisk],
    *,
    max_items: int,
) -> tuple[list[OpenRisk], list[OpenRisk], int]:
    """按「新增优先、再未解决」截取风险条目。"""
    if max_items <= 0:
        return [], [], len(added) + len(unresolved)
    a = added[:max_items]
    remain = max_items - len(a)
    u = unresolved[:remain] if remain > 0 else []
    omitted = max(0, len(added) + len(unresolved) - len(a) - len(u))
    return a, u, omitted


def _fmt_week_span(start: datetime, end: datetime) -> str:
    """极简周区间：7.29-8.5"""
    return f"{start.month}.{start.day}-{end.month}.{end.day}"


def _weekly_action_done_bit(r: TaskProgressRow) -> str:
    """Task 行：Action 完成数（近黑、明细字号）。"""
    total = max(0, int(r.action_count or 0))
    done = max(0, int(r.done_count or 0))
    return _font("text", f"完成 {done}/{total}", size=_DINGTALK_FONT_SIZE_META)


def _format_weekly_task_section(
    rows: list[TaskProgressRow],
    *,
    max_rows: int,
    section_title: str = "**📌 本周 Task**",
    empty_hint: str = "本周暂无 Task / Action",
) -> tuple[list[str], int]:
    """
    周报 Task 区块：每 Task 一行摘要（领域+标题 · 负责人 · 进度 · 完成数 · 风险数）。

    不展开 Action / 风险正文；排序由上游 collect 完成（风险多→进度低优先）。
    """
    if max_rows <= 0:
        if not rows:
            return ([_font("comment", empty_hint), ""], 0)
        return ([_font("comment", "Task 明细已省略")], len(rows))
    shown = rows[:max_rows]
    omitted = max(0, len(rows) - len(shown))
    parts: list[str] = [section_title, ""]
    if not shown:
        parts.append(_font("comment", empty_hint))
        parts.append("")
        return parts, 0

    for idx, r in enumerate(shown, 1):
        title = _clip(r.task_title, 48)
        # 黑为主：标题近黑加粗；领域少量蓝；负责人灰；进度默认黑，落后才橙；风险橙点缀
        task_label = (
            f"{_font('domain', f'[{r.domain_name}]')} "
            f"**{_font('text', title)}**"
        )
        prog = _font(_weekly_progress_tone(r.progress_avg), f"{r.progress_avg}%")
        done_bit = _weekly_action_done_bit(r)
        lead = (r.lead_name or "").strip()
        lead_bit = f" · {_font('comment', lead)}" if lead else ""
        if r.risk_count > 0:
            head = (
                f"**{_dingtalk_index(idx)}** {task_label}{lead_bit}  "
                f"{prog} · {done_bit} · {_font('warning', f'阻塞 {r.risk_count}')}"
            )
        else:
            head = (
                f"**{_dingtalk_index(idx)}** {task_label}{lead_bit}  "
                f"{prog} · {done_bit}"
            )
        # 列表 + 空行 + <br>：钉钉 markdown 对纯换行不稳定，避免多 Task 粘成一段
        parts.append(f"- {head}")
        parts.append("")
        parts.append("<br>")
        parts.append("")

    return parts, omitted


def _domain_avg_line(rows: list[TaskProgressRow]) -> str:
    """保留函数供测试/兼容；周报正文不再展示分领域进度。"""
    bucket: dict[str, list[int]] = {}
    for r in rows:
        bucket.setdefault(r.domain_name, []).append(r.progress_avg)
    if not bucket:
        return ""
    bits = []
    for name in sorted(bucket.keys()):
        vals = bucket[name]
        avg = int(round(sum(vals) / len(vals))) if vals else 0
        bits.append(f"{name} {_font(_progress_tone(avg), f'{avg}%')}")
    return "　".join(bits)


def build_daily_brief_markdown(
    *,
    title: str,
    detail_url: str,
    brief: str = "今日大屏 Action 明细见下图；完整交互请点详情链接打开大屏。",
    image_data_uri: str | None = None,
) -> str:
    """
    日报精简正文：标题 + 少量说明 +（可选）图 + 详情链接。

    不含阻塞列表 / 进度统计。
    """
    parts: list[str] = [
        f"### {title}",
        "",
        (brief or "").strip(),
        "",
    ]
    if image_data_uri:
        parts.append(f"![]({image_data_uri})")
        parts.append("")
    url = (detail_url or "").strip()
    if url:
        parts.append(f"**详情大屏**：[点此打开]({url})")
        parts.append(_font("comment", url, size=_DINGTALK_FONT_SIZE_META))
    return "\n".join(parts).strip()


def build_daily_link_markdown(
    *,
    today: date,
    screenshot_ok: bool = True,
    image_data_uri: str | None = None,
    image_part: int | None = None,
    image_parts: int | None = None,
) -> str:
    """
    日报正文：标题 +（可选）内嵌大屏切片 + 详情深链。

    image_data_uri：data:image/jpeg;base64,...（钉钉自定义机器人无法用公网拉内网图，故内嵌）。
    """
    parts: list[str] = [
        f"### {daily_report_heading(today)}",
        "",
    ]
    if image_data_uri:
        if image_part is not None and image_parts is not None and image_parts > 1:
            parts.append(_font("comment", f"今日大屏（{image_part}/{image_parts}）"))
            parts.append("")
        parts.append(f"![]({image_data_uri})")
        parts.append("")
    elif not screenshot_ok:
        parts.append(_font("comment", "今日大屏截图未生成，请点详情查看"))
        parts.append("")
    parts.extend(_report_footer())
    return "\n".join(parts).strip()


def build_daily_slice_markdown(
    *,
    today: date,
    image_data_uri: str,
    image_part: int,
    image_parts: int,
) -> str:
    """续片：仅标题小字 + 图（仍带关键词所需的日报标题信息）。"""
    parts: list[str] = [
        f"### {daily_report_heading(today)}（续 {image_part}/{image_parts}）",
        "",
        f"![]({image_data_uri})",
    ]
    return "\n".join(parts).strip()


def build_daily_markdown(
    *,
    today: date,
    diff: RiskDiff,
    summary: ProgressSummary | None = None,
    buckets: ActionProgressBuckets | None = None,
    action_lines: list[TodayActionLine] | None = None,
    max_risk_items: int | None = None,
    note_max: int = 48,
    risk_max: int = 48,
    ultra_compact: bool = False,
    expand_risk_section: bool | None = None,
    risk_layout: str = "block",
    risk_title_max: int = 18,
    max_action_lines: int | None = None,
) -> str:
    """
    日报结构（文字版，保留供 dry_run / 兼容）：
    1) 当前阻塞（域 / Task / Action / 阻塞 分行标注）
    2) Action 进度统计（已完成 / 无进度 / 0–50 / 50–100）
    3) 详情链接
    action_lines / note_max / max_action_lines 保留兼容旧调用，正文不再展示进展明细。
    """
    del action_lines, note_max, max_action_lines  # 兼容旧签名
    added_all = sorted(diff.added, key=lambda r: (r.progress, r.domain_name, r.action_title))
    unresolved_all = sorted(
        diff.unresolved, key=lambda r: (r.progress, r.domain_name, r.action_title)
    )
    risk_cap = (
        len(added_all) + len(unresolved_all)
        if max_risk_items is None
        else max_risk_items
    )
    added, unresolved, risk_omitted = _pick_risks_for_message(
        added_all, unresolved_all, max_items=risk_cap
    )
    if expand_risk_section is None:
        show_risk_detail = risk_layout != "none"
    else:
        show_risk_detail = bool(expand_risk_section) and risk_layout != "none"
    layout = risk_layout if show_risk_detail else "none"

    parts: list[str] = [
        f"### {daily_report_heading(today)}",
        "",
    ]
    if summary is not None:
        block_n = summary.risk_action_count
        parts.extend(
            [
                "**🔹 Action 速览**",
                (
                    f"> 本周 Action {_font('text', str(summary.action_count))}　"
                    f"当前有阻塞 {_font('warning' if block_n else 'text', str(block_n))}"
                ),
                "",
            ]
        )

    parts.append(_blocker_section_title("当前阻塞"))
    parts.append("")
    open_risks = list(added) + list(unresolved)
    if layout != "none" and risk_max > 0:
        if open_risks:
            if layout == "plain":
                parts.extend(
                    _risk_line_plain(
                        r, index=i, text_max=risk_max, title_max=risk_title_max
                    )
                    for i, r in enumerate(open_risks, 1)
                )
            elif layout == "block":
                parts.extend(
                    _risk_block(r, index=i, tone="warning", text_max=risk_max)
                    for i, r in enumerate(open_risks, 1)
                )
            else:
                parts.extend(
                    _risk_line_compact(r, index=i, tone="warning", text_max=risk_max)
                    for i, r in enumerate(open_risks, 1)
                )
            parts.append("")
        else:
            parts.append(_font("comment", "本日无开放阻塞（或均已消除）"))
            parts.append("")
    else:
        if len(diff.added) + len(diff.unresolved) == 0:
            parts.append(_font("comment", "本日无开放阻塞（或均已消除）"))
        else:
            parts.append(_font("comment", "阻塞明细未展开"))
        parts.append("")
    if risk_omitted > 0:
        log.info("daily blocker_omitted=%s (message suppresses 另有文案)", risk_omitted)

    # —— Action 进度四档统计（标题换行；标签与数字统一近黑） ——
    b = buckets or ActionProgressBuckets()
    parts.append("**📊 Action 进度统计**")
    parts.append("")
    parts.append(
        (
            f"{_font('text', '已完成', size=_DINGTALK_FONT_SIZE_META)} "
            f"**{_font('text', str(b.done), size=_DINGTALK_FONT_SIZE_META)}**　"
            f"{_font('text', '无进度', size=_DINGTALK_FONT_SIZE_META)} "
            f"**{_font('text', str(b.no_update_today), size=_DINGTALK_FONT_SIZE_META)}**　"
            f"{_font('text', '0–50%', size=_DINGTALK_FONT_SIZE_META)} "
            f"**{_font('text', str(b.progress_0_50), size=_DINGTALK_FONT_SIZE_META)}**　"
            f"{_font('text', '50–100%', size=_DINGTALK_FONT_SIZE_META)} "
            f"**{_font('text', str(b.progress_50_100), size=_DINGTALK_FONT_SIZE_META)}**"
        )
    )
    parts.extend(_report_footer())
    return "\n".join(parts).strip()


def _weekly_focus_rows(
    rows: list[TaskProgressRow], *, limit: int | None = None
) -> list[TaskProgressRow]:
    """高阻塞 Task（重点关注）；limit=None 表示全部，否则取前 N。"""
    blocked = [r for r in rows if r.risk_count > 0]
    if limit is None:
        return blocked
    return blocked[: max(0, int(limit))]


def _weekly_conclusion_body(
    *,
    summary: ProgressSummary,
    risk_task_n: int,
    diff: RiskDiff,
) -> str:
    """
    周报结论文案（不含「本周结论」标题）：点明阻塞态势与优先处理。
    展示顺序由 build_weekly_markdown 控制：标题 → KPI → 本文。
    """
    avg = summary.progress_avg
    added_n = len(diff.added or [])
    change_bits: list[str] = []
    if added_n:
        change_bits.append(f"新增 {_font('warning', str(added_n))}")
    change = f"；本周{'、'.join(change_bits)}" if change_bits else ""

    if risk_task_n > 0:
        return (
            f"{_font('text', str(summary.task_count))} Task 中 "
            f"{_font('warning', str(risk_task_n))} 个有阻塞，"
            f"请优先处理下方{_font('warning', '重点关注')}"
            f"{change}"
        )
    if avg >= 80:
        return (
            f"{_font('text', str(summary.task_count))} Task，"
            f"{_font('text', '暂无开放阻塞，整体推进平稳')}"
            f"{change}"
        )
    return (
        f"{_font('text', str(summary.task_count))} Task，"
        f"{_font('text', '暂无开放阻塞')}"
        f"{change}"
    )


def _weekly_conclusion_parts(
    *,
    summary: ProgressSummary,
    risk_task_n: int,
    diff: RiskDiff,
) -> list[str]:
    """兼容旧调用：标题与结论文案同行（现周报正文已拆成三行，优先用 body）。"""
    body = _weekly_conclusion_body(
        summary=summary, risk_task_n=risk_task_n, diff=diff
    )
    return [f"**{_DINGTALK_WEEKLY_CONCLUSION_MARK} 本周结论**　{body}"]


def _weekly_focus_parts(focus: list[TaskProgressRow]) -> list[str]:
    """重点关注：高阻塞 Task（含负责人+进度+完成数）。"""
    title = _blocker_section_title("重点关注")
    if not focus:
        return [
            title,
            "",
            _font("comment", "本周暂无开放阻塞 Task"),
            "",
        ]
    parts: list[str] = [
        title,
        "",
    ]
    for r in focus:
        title = _clip(r.task_title, 28)
        lead = (r.lead_name or "").strip()
        lead_bit = (
            f" · {_font('comment', lead, size=_DINGTALK_FONT_SIZE_META)}" if lead else ""
        )
        prog = _font(
            _weekly_progress_tone(r.progress_avg),
            f"{r.progress_avg}%",
            size=_DINGTALK_FONT_SIZE_META,
        )
        done_bit = _weekly_action_done_bit(r)
        parts.append(
            f"- {_font('domain', f'[{r.domain_name}]', size=_DINGTALK_FONT_SIZE_TITLE)} "
            f"**{_font('text', title, size=_DINGTALK_FONT_SIZE_TITLE)}**{lead_bit}  "
            f"{prog} · {done_bit} · "
            f"{_font('warning', f'阻塞 {r.risk_count}', size=_DINGTALK_FONT_SIZE_META)}"
        )
        parts.append("")
    parts.append("<br>")
    parts.append("")
    return parts


def build_weekly_markdown(
    *,
    summary: ProgressSummary,
    diff: RiskDiff,
    task_rows: list[TaskProgressRow] | None = None,
    max_task_rows: int | None = None,
    max_focus_rows: int | None = None,
) -> str:
    """
    周报结构：
    1) 标题行（含周区间小字）
    2) 📋 本周结论（仅标题）
    3) KPI：完成 / 均进度 / 阻塞 Task / 新增
    4) 结论文案（有多少阻塞 + 优先处理）
    5) 重点关注（全部阻塞 Task；max_focus_rows 可截前几条）
    6) 详情链接
    max_task_rows 保留兼容，正文不再列「其余进行中」。
    """
    del max_task_rows
    rows = list(task_rows or [])
    risk_task_n = sum(1 for r in rows if r.risk_count > 0)
    added_n = len(diff.added or [])
    done_n = int(summary.done_count or 0)
    total_n = max(0, int(summary.action_count or 0))

    focus = _weekly_focus_rows(rows, limit=max_focus_rows)
    week_span = _fmt_week_span(summary.week_start, summary.week_end)

    parts: list[str] = [
        (
            f"### {weekly_report_heading()} "
            f"{_font('comment', week_span, size=_DINGTALK_FONT_SIZE_META)}"
        ),
        "",
        f"**{_DINGTALK_WEEKLY_CONCLUSION_MARK} 本周结论**",
        "",
        (
            f"{_font('text', '完成', size=_DINGTALK_FONT_SIZE_META)} "
            f"**{_font('text', f'{done_n}/{total_n}', size=_DINGTALK_FONT_SIZE_META)}**　"
            f"{_font('text', '均进度', size=_DINGTALK_FONT_SIZE_META)} "
            f"**{_font('text', f'{summary.progress_avg}%', size=_DINGTALK_FONT_SIZE_META)}**　"
            f"{_font('text', '阻塞 Task', size=_DINGTALK_FONT_SIZE_META)} "
            f"**{_font('text', str(risk_task_n), size=_DINGTALK_FONT_SIZE_META)}**　"
            f"{_font('text', '新增', size=_DINGTALK_FONT_SIZE_META)} "
            f"**{_font('text', str(added_n), size=_DINGTALK_FONT_SIZE_META)}**"
        ),
        "",
        _weekly_conclusion_body(
            summary=summary, risk_task_n=risk_task_n, diff=diff
        ),
        "",
    ]
    parts.extend(_weekly_focus_parts(focus))
    parts.extend(_report_footer())
    return "\n".join(parts).strip()


def utf8_len(text: str) -> int:
    return len(text.encode("utf-8"))


def _hard_truncate(content: str, max_bytes: int) -> str:
    raw = content.encode("utf-8")
    if len(raw) <= max_bytes:
        return content
    suffix = "\n\n…(已截断)"
    budget = max_bytes - len(suffix.encode("utf-8"))
    if budget < 64:
        budget = max_bytes
        suffix = ""
    cut = raw[:budget]
    while cut and (cut[-1] & 0xC0) == 0x80:
        cut = cut[:-1]
    return cut.decode("utf-8", errors="ignore") + suffix


def _strip_llm_fence(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        lines = t.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    return t


async def _ai_compress_push_markdown(
    content: str,
    *,
    kind: str,
    max_bytes: int,
) -> str | None:
    """
    调用 LLM 压缩钉钉 markdown：保留全部 Task/Action/风险事实，去掉废话与重复。
    失败返回 None（由调用方兜底）。
    """
    if not PUSH_AI_COMPRESS_ENABLED:
        log.warning(
            "push AI compress skipped: DINGTALK_PUSH_AI_COMPRESS is disabled (kind=%s)",
            kind,
        )
        return None
    log.info(
        "push AI compress start kind=%s in_bytes=%s timeout=%ss",
        kind,
        utf8_len(content),
        PUSH_AI_COMPRESS_TIMEOUT_SEC,
    )
    try:
        out = await asyncio.wait_for(
            _ai_compress_push_markdown_inner(content, kind=kind, max_bytes=max_bytes),
            timeout=PUSH_AI_COMPRESS_TIMEOUT_SEC,
        )
        if out:
            log.info(
                "push AI compress ok kind=%s out_bytes=%s",
                kind,
                utf8_len(out),
            )
        else:
            log.warning("push AI compress returned empty kind=%s", kind)
        return out
    except asyncio.TimeoutError:
        log.warning("push AI compress timeout after %ss", PUSH_AI_COMPRESS_TIMEOUT_SEC)
        return None


async def _ai_compress_push_markdown_inner(
    content: str,
    *,
    kind: str,
    max_bytes: int,
) -> str | None:
    target = min(PUSH_AI_COMPRESS_TARGET_BYTES, max(512, max_bytes - 120))
    label = "测试日报" if kind == "daily" else "测试周报"
    # 输入过长时先截到合理长度，降低空结果概率
    src = content
    if utf8_len(src) > 12000:
        src = _hard_truncate(src, 12000).rsplit("…(已截断)", 1)[0]
    prompt = (
        f"你是{label}编辑。把下面钉钉群 markdown 压缩到 UTF-8 约 {target} 字节以内（硬上限 {max_bytes}）。\n"
        "必须遵守：\n"
        "1) 不得删除任何 Task / Action / 风险条目，可用极短措辞保留要点；\n"
        "2) 去掉客套、重复、无信息说明；进度%与风险关键词必须保留；\n"
        "3) 尽量保留 <font color=\"...\"> 与 **加粗** 和 Task 分组空行；\n"
        "4) 只输出压缩后的 markdown 正文，不要解释、不要代码围栏。\n\n"
        f"原文：\n{src}"
    )
    try:
        from app.ai_service.client import chat
        from app.ai_service.exceptions import LLMError, LLMNotConfiguredError

        # 推送场景：少重试，快速失败交给确定性压缩
        out = await chat(
            [{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=8192,
            think=False,
            max_retries=1,
            base_delay_ms=400,
        )
        out = _strip_llm_fence(out)
        if not out:
            return None
        if utf8_len(out) > max_bytes:
            out2 = await chat(
                [
                    {
                        "role": "user",
                        "content": (
                            f"再压缩下面内容，UTF-8 必须 ≤{max_bytes} 字节，"
                            f"仍须保留全部条目与颜色标签，只输出 markdown：\n{out}"
                        ),
                    }
                ],
                temperature=0.1,
                max_tokens=8192,
                think=False,
                max_retries=1,
                base_delay_ms=400,
            )
            out2 = _strip_llm_fence(out2)
            return out2 or out
        return out
    except LLMNotConfiguredError as e:
        log.warning("push AI compress skipped: %s", e)
        return None
    except LLMError as e:
        log.warning("push AI compress failed: %s", e)
        return None
    except Exception as e:
        log.warning("push AI compress unexpected: %s", e)
        return None



async def _ai_summarize_daily_fields(
    lines: list[TodayActionLine],
    *,
    max_bytes: int,
) -> list[TodayActionLine] | None:
    """
    让 AI 把每条 Action 的说明/风险总结成短句，返回新的 TodayActionLine 列表。
    分批请求，避免单次过长导致超时/空结果。失败返回 None。
    """
    if not PUSH_AI_COMPRESS_ENABLED or not lines:
        return None

    batch_size = 5
    by_i: dict[int, dict] = {}
    try:
        for start in range(0, len(lines), batch_size):
            chunk = list(enumerate(lines))[start : start + batch_size]
            payload = [
                {
                    "i": idx,
                    "title": (row.action_title or "")[:40],
                    "note": (row.note or "")[:80],
                    "risk": (row.risk or "")[:80],
                }
                for idx, row in chunk
            ]
            prompt = (
                "你是测试日报编辑。为下面每条生成更短总结。"
                "note_summary/risk_summary 各 ≤28 字；无原文则空串；"
                '只输出 JSON 数组 [{"i":0,"note_summary":"...","risk_summary":"..."}]，'
                "不要解释。\n"
                f"{json.dumps(payload, ensure_ascii=False)}"
            )
            # MiniMax 在 max_tokens 较大时更稳（避免 reasoning 占满导致空 content）
            per_batch_timeout = max(40.0, PUSH_AI_COMPRESS_TIMEOUT_SEC)
            raw = await asyncio.wait_for(
                _ai_summarize_daily_fields_inner(prompt),
                timeout=per_batch_timeout,
            )
            if not raw:
                log.warning("daily AI field summarize empty batch start=%s", start)
                return None
            text = _strip_llm_fence(raw)
            a = text.find("[")
            if a < 0:
                log.warning("daily AI field summarize no JSON array batch start=%s", start)
                return None
            try:
                data, _end = json.JSONDecoder().raw_decode(text[a:])
            except json.JSONDecodeError as e:
                log.warning("daily AI field summarize JSON error batch=%s: %s", start, e)
                return None
            if not isinstance(data, list):
                return None
            for item in data:
                if isinstance(item, dict) and "i" in item:
                    by_i[int(item["i"])] = item
    except asyncio.TimeoutError:
        log.warning("daily AI field summarize timeout")
        return None
    except Exception as e:
        log.warning("daily AI field summarize failed: %s", e)
        return None

    if len(by_i) < max(1, len(lines) // 2):
        log.warning(
            "daily AI field summarize incomplete got=%s need~%s",
            len(by_i),
            len(lines),
        )
        return None

    out: list[TodayActionLine] = []
    for idx, row in enumerate(lines):
        item = by_i.get(idx) or {}
        note_s = str(item.get("note_summary") or "").strip()
        risk_s = str(item.get("risk_summary") or "").strip()
        if row.note and not note_s:
            note_s = _brief_text(row.note, 24)
        if row.risk and not risk_s:
            risk_s = _brief_text(row.risk, 24)
        out.append(
            replace(
                row,
                note=note_s if row.note else "",
                risk=risk_s if row.risk else "",
            )
        )
    return out


async def _ai_summarize_daily_fields_inner(prompt: str) -> str | None:
    try:
        from app.ai_service.client import chat
        from app.ai_service.exceptions import LLMError, LLMNotConfiguredError

        # think=False + 大 max_tokens：reasoning_split 下仍能留下 content；过小易空结果/超时
        out = await chat(
            [{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=8192,
            think=False,
            max_retries=1,
            base_delay_ms=400,
        )
        return out or None
    except LLMNotConfiguredError as e:
        log.warning("daily AI field summarize skipped: %s", e)
        return None
    except LLMError as e:
        log.warning("daily AI field summarize failed: %s", e)
        return None
    except Exception as e:
        log.warning("daily AI field summarize unexpected: %s", e)
        return None


def _shrink_lines_for_fit(
    lines: list[TodayActionLine], *, note_max: int, risk_max: int
) -> list[TodayActionLine]:
    """确定性缩短说明/风险字段（不删条目）。"""
    out: list[TodayActionLine] = []
    for row in lines:
        out.append(
            replace(
                row,
                risk=_brief_text(row.risk, risk_max) if row.risk and risk_max > 0 else "",
                note=_brief_text(row.note, note_max) if row.note and note_max > 0 else "",
            )
        )
    return out


def _sync_diff_risk_text_from_lines(
    diff: RiskDiff, lines: list[TodayActionLine]
) -> RiskDiff:
    """把 AI/压缩后的 Action 风险文案同步到风险区（避免风险区仍用长原文再被截断）。"""
    by_id = {x.action_id: x for x in lines if x.action_id}

    def _map(r: OpenRisk) -> OpenRisk:
        row = by_id.get(r.action_id)
        if row is not None and (row.risk or "").strip():
            return replace(r, risk=row.risk.strip())
        return r

    return RiskDiff(
        added=[_map(x) for x in diff.added],
        unresolved=[_map(x) for x in diff.unresolved],
        resolved_ids=list(diff.resolved_ids),
        current={k: _map(v) for k, v in (diff.current or {}).items()},
    )


def _local_summarize_lines(lines: list[TodayActionLine]) -> list[TodayActionLine]:
    """
    AI 不可用时的本地总结：取首句/前若干完整意群，不打省略号半截。
    """
    out: list[TodayActionLine] = []
    for row in lines:
        note = (row.note or "").replace("\n", " ").strip()
        risk = (row.risk or "").replace("\n", " ").strip()
        if note:
            for sep in ("。", "；", ";", "！", "？"):
                if sep in note:
                    note = note.split(sep, 1)[0].strip() + (sep if sep in "。！？" else "")
                    break
            if len(note) > 36:
                note = _full_or_summary(note, 36) or note[:36]
        if risk:
            for sep in ("。", "；", ";", "！", "？"):
                if sep in risk:
                    risk = risk.split(sep, 1)[0].strip() + (sep if sep in "。！？" else "")
                    break
            if len(risk) > 36:
                risk = _full_or_summary(risk, 36) or risk[:36]
        out.append(replace(row, note=note, risk=risk))
    return out


async def fit_daily_markdown(
    *,
    today: date,
    diff: RiskDiff,
    summary: ProgressSummary | None = None,
    buckets: ActionProgressBuckets | None = None,
    action_lines: list[TodayActionLine] | None = None,
    max_bytes: int = WECOM_MSG_MAX_BYTES,
) -> str:
    """
    日报适配单条上限：
    1) 全文（阻塞列表 + 进度统计）；
    2) 超长 → AI 总结阻塞文案（可借 action_lines / OpenRisk）；
    3) 仍超 → AI 压整篇；
    4) 再不行 → 压短阻塞文案 / plain；阻塞尽量全列；
    5) 硬截断兜底。
    """
    del action_lines  # 日报正文不再展示进展明细；保留参数兼容
    work_diff = diff
    bucket = buckets or ActionProgressBuckets()

    def _build(
        *,
        src_diff: RiskDiff | None = None,
        risk_max: int = 80,
        risk_layout: str = "list",
        risk_title_max: int = 18,
        expand_risk: bool = True,
    ) -> str:
        return build_daily_markdown(
            today=today,
            diff=src_diff if src_diff is not None else work_diff,
            summary=summary,
            buckets=bucket,
            max_risk_items=None,
            risk_max=risk_max,
            expand_risk_section=expand_risk,
            risk_layout=risk_layout,
            risk_title_max=risk_title_max,
        )

    def _shrink_open_risks(src: RiskDiff, risk_chars: int) -> RiskDiff:
        def _one(r: OpenRisk) -> OpenRisk:
            short = _full_or_summary(r.risk, risk_chars) or (
                (r.risk or "")[:risk_chars] if r.risk else ""
            )
            return replace(r, risk=short)

        return RiskDiff(
            added=[_one(x) for x in src.added],
            unresolved=[_one(x) for x in src.unresolved],
            resolved_ids=list(src.resolved_ids),
            current={k: _one(v) for k, v in (src.current or {}).items()},
        )

    full = _build(risk_max=80, risk_layout="block")
    if utf8_len(full) <= max_bytes:
        return full

    log.warning("daily oversized (%s), try AI compress / shrink blockers", utf8_len(full))
    # 用 OpenRisk 转成伪 Action 行，复用字段总结
    open_all = list(diff.added) + list(diff.unresolved)
    pseudo_lines = [
        TodayActionLine(
            action_id=r.action_id,
            task_id=r.task_id or "",
            owner_name=r.owner_name,
            domain_name=r.domain_name,
            task_title=r.task_title,
            action_title=r.action_title,
            progress=r.progress,
            risk=r.risk,
            note="",
            status=STATUS_PUBLISHED,
        )
        for r in open_all
    ]
    summarized = await _ai_summarize_daily_fields(pseudo_lines, max_bytes=max_bytes)
    if summarized:
        work_diff = _sync_diff_risk_text_from_lines(diff, summarized)
    else:
        work_diff = _shrink_open_risks(diff, 36)

    for layout in ("block", "list", "plain"):
        candidate = _build(src_diff=work_diff, risk_max=48, risk_layout=layout)
        n = utf8_len(candidate)
        log.info("daily after-summary layout=%s bytes=%s", layout, n)
        if n <= max_bytes:
            return candidate

    best = _build(src_diff=work_diff, risk_max=48, risk_layout="list")
    compressed = await _ai_compress_push_markdown(best, kind="daily", max_bytes=max_bytes)
    if compressed and utf8_len(compressed) <= max_bytes:
        return compressed
    if compressed and utf8_len(compressed) < utf8_len(best):
        best = compressed

    for risk_chars, title_max, layout in (
        (28, 22, "list"),
        (20, 18, "list"),
        (14, 16, "list"),
        (10, 14, "list"),
        # 优先继续压阻塞文案、保留 Action 名，避免只剩 Task 像一段话
        (8, 14, "list"),
        (6, 14, "list"),
        (4, 12, "list"),
        (3, 10, "list"),
        (3, 8, "plain"),
        (2, 6, "plain"),  # 最后才藏 Action
    ):
        work_diff2 = _shrink_open_risks(work_diff, risk_chars)
        candidate = _build(
            src_diff=work_diff2,
            risk_max=risk_chars,
            risk_layout=layout,
            risk_title_max=title_max,
        )
        n = utf8_len(candidate)
        log.info(
            "daily blockers risk_chars=%s layout=%s bytes=%s",
            risk_chars,
            layout,
            n,
        )
        if n <= max_bytes:
            return candidate
        if n < utf8_len(best):
            best = candidate

    log.error(
        "daily cannot fit under %s (shortest=%s); hard truncate as last resort",
        max_bytes,
        utf8_len(best),
    )
    return _hard_truncate(best, max_bytes)



def _format_daily_action_skeleton(lines: list[TodayActionLine]) -> list[str]:
    """极限骨架进展区：颜色 + 组间空行；风险已在上方风险区，此处不再重复。"""
    parts: list[str] = [f"**📌 今日进展**（{len(lines)}）", ""]
    if not lines:
        parts.append(_font("comment", "今日暂无日更"))
        parts.append("")
        return parts
    cur_task_id: str | None = None
    for row in lines:
        if row.task_id != cur_task_id:
            if cur_task_id is not None:
                parts.append("")
            cur_task_id = row.task_id
            domain = (row.domain_name or "—").strip() or "—"
            task_label = _clip(row.task_title, 28) or "（无标题）"
            parts.append(f"{_font('domain', f'【{domain}】')} **{task_label}**")
        prog = _font(_progress_tone(row.progress), f"{row.progress}%")
        note_bit = (
            f"　{_font('comment', _brief_text(row.note, 10))}" if row.note else ""
        )
        parts.append(
            f"- {_font('text', _clip(row.action_title, 26))} {prog}{note_bit}"
        )
    parts.append("")
    return parts


def _format_daily_risk_skeleton(diff: RiskDiff) -> list[str]:
    """骨架版风险区（放在进展之前）；标题仅「当前风险」。"""
    parts = [_blocker_section_title("当前风险"), ""]
    open_rows = sorted(
        list(diff.added) + list(diff.unresolved),
        key=lambda r: (r.progress, r.domain_name, r.action_title),
    )
    if not open_rows:
        parts.append(_font("comment", "本日无开放风险（或均已消除）"))
        parts.append("")
        return parts
    for r in open_rows:
        risk_txt = _brief_text(r.risk, 40) or (r.risk or "").strip()
        domain = (r.domain_name or "—").strip() or "—"
        parts.append(
            f"- {_font('domain', f'[{domain}]')} "
            f"{_font('text', _clip(r.action_title, 22))}"
            f"　{_font('warning', risk_txt)}"
        )
    parts.append("")
    return parts


def build_daily_skeleton_markdown(
    *,
    today: date,
    diff: RiskDiff,
    summary: ProgressSummary | None = None,
    buckets: ActionProgressBuckets | None = None,
    action_lines: list[TodayActionLine] | None = None,
) -> str:
    """极限压缩版：阻塞 plain + 进度统计。"""
    del action_lines
    return build_daily_markdown(
        today=today,
        diff=diff,
        summary=summary,
        buckets=buckets,
        risk_max=12,
        risk_layout="plain",
        risk_title_max=14,
        expand_risk_section=True,
    )


def _flat_weekly_risks(
    rows: list[TaskProgressRow],
) -> list[tuple[int, int, TaskRiskItem]]:
    """展平 (task_idx, item_idx, item)，供周报阻塞总结。"""
    out: list[tuple[int, int, TaskRiskItem]] = []
    for ti, row in enumerate(rows):
        items = list(row.risk_items or [])
        if not items and row.risk_texts:
            items = [TaskRiskItem(action_title="", risk=t) for t in row.risk_texts]
        for ii, it in enumerate(items):
            out.append((ti, ii, it))
    return out


def _apply_weekly_risk_map(
    rows: list[TaskProgressRow],
    risk_by_key: dict[tuple[int, int], str],
) -> list[TaskProgressRow]:
    """按 (task_idx, item_idx) 写回总结后的风险文案。"""
    out: list[TaskProgressRow] = []
    for ti, row in enumerate(rows):
        items = list(row.risk_items or [])
        if not items and row.risk_texts:
            items = [TaskRiskItem(action_title="", risk=t) for t in row.risk_texts]
        new_items: list[TaskRiskItem] = []
        for ii, it in enumerate(items):
            risk = risk_by_key.get((ti, ii), it.risk)
            new_items.append(replace(it, risk=risk if (it.risk or "").strip() else ""))
        out.append(
            replace(
                row,
                risk_items=new_items,
                risk_texts=[x.risk for x in new_items],
                risk_count=max(row.risk_count, len(new_items)) if new_items else row.risk_count,
            )
        )
    return out


def _local_summarize_weekly_rows(rows: list[TaskProgressRow]) -> list[TaskProgressRow]:
    """AI 不可用时：取风险首句/完整意群，不打省略号半截。"""
    risk_map: dict[tuple[int, int], str] = {}
    for ti, ii, it in _flat_weekly_risks(rows):
        risk = (it.risk or "").replace("\n", " ").strip()
        if not risk:
            risk_map[(ti, ii)] = ""
            continue
        for sep in ("。", "；", ";", "！", "？"):
            if sep in risk:
                risk = risk.split(sep, 1)[0].strip() + (sep if sep in "。！？" else "")
                break
        if len(risk) > 36:
            risk = _full_or_summary(risk, 36) or risk[:36]
        risk_map[(ti, ii)] = risk
    return _apply_weekly_risk_map(rows, risk_map)


def _shrink_weekly_rows(rows: list[TaskProgressRow], *, risk_max: int) -> list[TaskProgressRow]:
    """确定性缩短周报风险字段（不删条目）。"""
    risk_map: dict[tuple[int, int], str] = {}
    for ti, ii, it in _flat_weekly_risks(rows):
        if risk_max <= 0 or not (it.risk or "").strip():
            risk_map[(ti, ii)] = ""
        else:
            risk_map[(ti, ii)] = _brief_text(it.risk, risk_max) or ""
    return _apply_weekly_risk_map(rows, risk_map)


async def _ai_summarize_weekly_risks(
    rows: list[TaskProgressRow],
    *,
    max_bytes: int,
) -> list[TaskProgressRow] | None:
    """
    让 AI 把周报各 Action 风险总结成短句；分批 JSON。失败返回 None。
    """
    flat = _flat_weekly_risks(rows)
    if not PUSH_AI_COMPRESS_ENABLED or not flat:
        return None

    # 周报风险条数常多于日报，批稍大以减少轮次、降低总超时概率
    batch_size = 8
    by_i: dict[int, dict] = {}
    try:
        for start in range(0, len(flat), batch_size):
            chunk = list(enumerate(flat))[start : start + batch_size]
            payload = [
                {
                    "i": gidx,
                    "title": (it.action_title or "")[:40],
                    "risk": (it.risk or "")[:120],
                }
                for gidx, (_ti, _ii, it) in chunk
            ]
            prompt = (
                "你是测试周报编辑。为下面每条风险生成更短总结。"
                "risk_summary ≤28 字；无原文则空串；"
                '只输出 JSON 数组 [{"i":0,"risk_summary":"..."}]，不要解释。\n'
                f"{json.dumps(payload, ensure_ascii=False)}"
            )
            per_batch_timeout = max(50.0, PUSH_AI_COMPRESS_TIMEOUT_SEC)
            raw = await asyncio.wait_for(
                _ai_summarize_daily_fields_inner(prompt),
                timeout=per_batch_timeout,
            )
            if not raw:
                log.warning("weekly AI risk summarize empty batch start=%s", start)
                return None
            text = _strip_llm_fence(raw)
            a = text.find("[")
            if a < 0:
                log.warning("weekly AI risk summarize no JSON array batch start=%s", start)
                return None
            try:
                data, _end = json.JSONDecoder().raw_decode(text[a:])
            except json.JSONDecodeError as e:
                log.warning("weekly AI risk summarize JSON error batch=%s: %s", start, e)
                return None
            if not isinstance(data, list):
                return None
            for item in data:
                if isinstance(item, dict) and "i" in item:
                    by_i[int(item["i"])] = item
    except asyncio.TimeoutError:
        log.warning("weekly AI risk summarize timeout")
        return None
    except Exception as e:
        log.warning("weekly AI risk summarize failed: %s", e)
        return None

    if len(by_i) < max(1, len(flat) // 2):
        log.warning(
            "weekly AI risk summarize incomplete got=%s need~%s",
            len(by_i),
            len(flat),
        )
        return None

    risk_map: dict[tuple[int, int], str] = {}
    for gidx, (ti, ii, it) in enumerate(flat):
        item = by_i.get(gidx) or {}
        risk_s = str(item.get("risk_summary") or "").strip()
        if (it.risk or "").strip() and not risk_s:
            risk_s = _brief_text(it.risk, 24)
        risk_map[(ti, ii)] = risk_s if (it.risk or "").strip() else ""
    _ = max_bytes  # 与日报签名对齐，便于后续按预算调批大小
    return _apply_weekly_risk_map(rows, risk_map)


async def fit_weekly_markdown(
    *,
    summary: ProgressSummary,
    diff: RiskDiff,
    task_rows: list[TaskProgressRow] | None = None,
    max_bytes: int = WECOM_MSG_MAX_BYTES,
) -> str:
    """
    周报适配单条上限（禁止拆条）：
    全文（重点关注尽量列全阻塞 Task）→ 超长则先截重点关注条数 → AI 压整篇 → 硬截断。
    """
    rows = list(task_rows or [])
    full = build_weekly_markdown(
        summary=summary,
        diff=diff,
        task_rows=rows,
        max_task_rows=None,
        max_focus_rows=None,
    )
    if utf8_len(full) <= max_bytes:
        return full

    focus_all = _weekly_focus_rows(rows, limit=None)
    if len(focus_all) > 1:
        log.warning(
            "weekly oversized (%s), shrink focus rows from %s",
            utf8_len(full),
            len(focus_all),
        )
        for n in range(len(focus_all) - 1, 0, -1):
            candidate = build_weekly_markdown(
                summary=summary,
                diff=diff,
                task_rows=rows,
                max_task_rows=None,
                max_focus_rows=n,
            )
            if utf8_len(candidate) <= max_bytes:
                return candidate
        candidate = build_weekly_markdown(
            summary=summary,
            diff=diff,
            task_rows=rows,
            max_task_rows=None,
            max_focus_rows=1,
        )
        if utf8_len(candidate) <= max_bytes:
            return candidate
        full = candidate

    log.warning("weekly still oversized (%s), try AI compress markdown", utf8_len(full))
    compressed = await _ai_compress_push_markdown(full, kind="weekly", max_bytes=max_bytes)
    if compressed and utf8_len(compressed) <= max_bytes:
        return compressed
    if compressed:
        return _hard_truncate(compressed, max_bytes)
    return _hard_truncate(full, max_bytes)


async def ensure_message_fits(content: str, *, max_bytes: int = WECOM_MSG_MAX_BYTES) -> str:
    """兼容旧调用：超长优先 AI 压缩，再硬截断。"""
    if utf8_len(content) <= max_bytes:
        return content
    compressed = await _ai_compress_push_markdown(content, kind="daily", max_bytes=max_bytes)
    if compressed and utf8_len(compressed) <= max_bytes:
        return compressed
    if compressed:
        return _hard_truncate(compressed, max_bytes)
    return _hard_truncate(content, max_bytes)


def daily_period_key(today: date | None = None) -> str:
    d = today or now_tm().date()
    return d.isoformat()


def weekly_period_key(ws: datetime | None = None) -> str:
    return week_key(ws or current_week_start())


# 供外部区分 kind
REPORT_KINDS = (REPORT_KIND_DAILY, REPORT_KIND_WEEKLY)
