"""
测试任务钉钉推送：开放风险采集、与上次快照对比、消息组装；日报偏 Action、周报偏 Task；单条 ≤4096，超长确定性缩短+硬截断（不调 AI）。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from sqlalchemy.orm import Session, joinedload

from app.auth.models import User
from app.test_manage.config import (
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
)
from app.test_manage.models import TmAction, TmDomain, TmPushSnapshot, TmTask, TmWeekPeriod
from app.test_manage.service import _latest_progress
from app.test_manage.week import current_week_start, daily_context_week_start, week_end, week_key

log = logging.getLogger("app.test_manage.push")


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
class RiskDiff:
    """相对上次快照的增量。"""

    added: list[OpenRisk] = field(default_factory=list)
    unresolved: list[OpenRisk] = field(default_factory=list)
    resolved_ids: list[str] = field(default_factory=list)
    current: dict[str, OpenRisk] = field(default_factory=dict)


@dataclass
class TodayActionLine:
    """日报：今日有日更的 Action 行（按负责人展示）。"""

    action_id: str
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
    """周报：Task 维度进度行（附带 Action 风险明细）。"""

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
    全项目：汇报周「进行中」Action 中，最新日更仍带 risk_blocker 的条目。

    优先 week_key_s（与看板活动周一致）；已完成 / 已取消 / 草稿不计入开放风险。
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
    out: dict[str, OpenRisk] = {}
    for a in actions:
        progress, risk = _latest_progress(a)
        risk = (risk or "").strip()
        if not risk:
            continue
        task = a.task
        domain = task.domain if task else None
        project = domain.project if domain else None
        out[a.id] = OpenRisk(
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
    return out


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
        p, risk = _latest_progress(a)
        progresses.append(p)
        if a.status == "published" and (risk or "").strip():
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


def collect_today_action_lines(
    db: Session,
    *,
    today: date,
    week_start: datetime | None = None,
    week_key_s: str | None = None,
) -> list[TodayActionLine]:
    """
    日报专用：汇报周内、今日有日更的 Action（Action 粒度）。
    按负责人姓名、领域、标题排序。
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
        lines.append(
            TodayActionLine(
                action_id=a.id,
                owner_name=names.get(a.owner_id, str(a.owner_id)),
                domain_name=(domain.name if domain else "") or "—",
                task_title=(task.title if task else "") or "",
                action_title=a.title,
                progress=int(du.progress_percent or 0),
                risk=(du.risk_blocker or "").strip(),
                note=(du.progress_note or "").strip(),
                status=a.status,
            )
        )
    lines.sort(key=lambda x: (x.owner_name, x.domain_name, x.action_title))
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
    names = _user_name_map(db, owner_ids)

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
            p, risk = _latest_progress(a)
            progresses.append(p)
            risk = (risk or "").strip()
            if a.status == STATUS_PUBLISHED and risk:
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


# 钉钉 markdown 着色（对齐企微 info=绿 / comment=灰 / warning=橙）
# 色号须用双引号，PC 与手机端才都能显示颜色
_DINGTALK_FONT_COLORS = {
    "info": "#00B578",
    "comment": "#8C8C8C",
    "warning": "#FF9200",
}


def _font(color: str, text: str) -> str:
    """钉钉 font 着色；语义与企微 info/comment/warning 对齐。"""
    hex_color = _DINGTALK_FONT_COLORS.get(color, _DINGTALK_FONT_COLORS["comment"])
    return f'<font color="{hex_color}">{text or ""}</font>'


def _progress_tone(percent: int) -> str:
    if percent < 50:
        return "warning"
    if percent < 80:
        return "comment"
    return "info"


def _clip(text: str, max_chars: int) -> str:
    s = (text or "").replace("\n", " ").strip()
    if len(s) <= max_chars:
        return s
    if max_chars <= 1:
        return "…"
    return s[: max_chars - 1] + "…"


def _risk_block(r: OpenRisk, *, index: int, tone: str = "warning") -> str:
    """
    Action 粒度风险行（日报主用）。
    tone: warning=新增；comment=未解决
    """
    risk = _clip(r.risk, WECOM_RISK_TEXT_MAX_CHARS)
    title = _clip(r.action_title, WECOM_RISK_TITLE_MAX_CHARS)
    prog_color = _progress_tone(r.progress)
    title_color = "warning" if tone == "warning" else "comment"
    return "\n".join(
        [
            f"> **{index}.** {_font(title_color, f'[{r.domain_name}] {title}')}"
            f" · **{r.owner_name}** · {_font(prog_color, f'{r.progress}%')}",
            f"> {_font('warning', risk)}",
        ]
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
            f"> **{index}.** {_font('warning', f'[{row.domain_name}] {title}')}"
            f"　{_font('warning', f'风险×{row.risk_count}')}",
            f"> {_font('warning', risk)}",
        ]
    )


def aggregate_open_risks_by_task(current: dict[str, OpenRisk]) -> list[TaskRiskRow]:
    """
    将 Action 开放风险聚合成 Task 行（周报用）。
    按 risk_count 降序；同一 Task 下多条风险文案用分号拼接去重。
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
                risk_summary="；".join(texts) if texts else "（有风险）",
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


def _status_tag(status: str) -> str:
    if status == STATUS_DONE:
        return "完成"
    if status == STATUS_DRAFT:
        return "草稿"
    return "进行中"


def _format_daily_action_section(
    lines: list[TodayActionLine], *, max_lines: int
) -> tuple[list[str], int]:
    """按负责人分组的今日 Action 进展；返回 (正文行, 省略数)。"""
    if max_lines <= 0:
        return ([_font("comment", "今日 Action 明细已省略，详见大屏")], len(lines))
    shown = lines[:max_lines]
    omitted = max(0, len(lines) - len(shown))
    parts: list[str] = ["**📌 今日 Action 进展（按负责人）**"]
    if not shown:
        parts.append(_font("comment", "今日暂无 Action 日更提交"))
        parts.append("")
        return parts, 0

    cur_owner = None
    for row in shown:
        if row.owner_name != cur_owner:
            cur_owner = row.owner_name
            parts.append(f"**{cur_owner}**")
        risk_bit = f"；风险：{_clip(row.risk, 40)}" if row.risk else ""
        note_bit = f" — {_clip(row.note, 40)}" if row.note else ""
        parts.append(
            f"- [{row.domain_name}] {_clip(row.action_title, 40)}"
            f"（{_status_tag(row.status)} {_font(_progress_tone(row.progress), f'{row.progress}%')}"
            f"{risk_bit}）{note_bit}"
        )
    parts.append("")
    return parts, omitted


def _fmt_week_span(start: datetime, end: datetime) -> str:
    """极简周区间：7.29-8.5"""
    return f"{start.month}.{start.day}-{end.month}.{end.day}"


def _format_weekly_task_section(
    rows: list[TaskProgressRow],
    *,
    max_rows: int,
    max_risks_per_task: int = 8,
) -> tuple[list[str], int]:
    """
    周报 Task 区块：Task 标题下挂 Action 风险（含 Action 名，避免不知归属）。
    """
    if max_rows <= 0:
        return ([_font("comment", "Task 明细已省略，详见大屏")], len(rows))
    shown = rows[:max_rows]
    omitted = max(0, len(rows) - len(shown))
    parts: list[str] = ["**📌 本周 Task**", ""]
    if not shown:
        parts.append(_font("comment", "本周暂无 Task / Action"))
        parts.append("")
        return parts, 0

    for idx, r in enumerate(shown, 1):
        title = _clip(r.task_title, 48)
        prog = _font(_progress_tone(r.progress_avg), f"{r.progress_avg}%")
        if r.risk_count > 0:
            head = (
                f"**{idx}. [{r.domain_name}] {title}**  "
                f"{prog} · {_font('warning', f'风险 {r.risk_count}')}"
            )
        else:
            head = f"**{idx}. [{r.domain_name}] {title}**  {prog}"
        parts.append(head)

        items = list(r.risk_items or [])
        if not items and r.risk_texts:
            items = [TaskRiskItem(action_title="", risk=t) for t in r.risk_texts]
        if items:
            for j, it in enumerate(items[:max_risks_per_task], 1):
                act = _clip(it.action_title, 28)
                risk = _clip(it.risk, WECOM_RISK_TEXT_MAX_CHARS)
                owner = (it.owner_name or "").strip()
                owner_bit = f" · **{owner}**" if owner else ""
                if act:
                    parts.append(
                        f"> {_font('warning', f'{j}.')} **{_clip(act, 28)}**"
                        f"{owner_bit} — {_font('warning', risk)}"
                    )
                else:
                    parts.append(
                        f"> {_font('warning', f'{j}.')}{owner_bit} {_font('warning', risk)}"
                    )
            extra = len(items) - max_risks_per_task
            if extra > 0:
                parts.append(f"> {_font('comment', f'另有 {extra} 条未列出')}")
        else:
            parts.append(f"> {_font('info', '✅ 暂无开放风险')}")
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


def build_daily_markdown(
    *,
    today: date,
    diff: RiskDiff,
    summary: ProgressSummary | None = None,
    action_lines: list[TodayActionLine] | None = None,
    max_risk_items: int = WECOM_PUSH_RISK_ITEMS_SOFT_MAX,
    max_action_lines: int = WECOM_DAILY_ACTION_LINES_SOFT_MAX,
) -> str:
    """
    日报：偏 Action + 当前风险。
    - 今日谁提交了哪些 Action 日更
    - 当前开放风险（新增 / 未解决）
    不展开 Task 总览（留给周报）。
    """
    lines = action_lines or []
    added_all = sorted(diff.added, key=lambda r: (r.progress, r.domain_name, r.action_title))
    unresolved_all = sorted(
        diff.unresolved, key=lambda r: (r.progress, r.domain_name, r.action_title)
    )
    added, unresolved, risk_omitted = _pick_risks_for_message(
        added_all, unresolved_all, max_items=max_risk_items
    )

    parts: list[str] = [
        "### 【测试日报】TestAI",
        f"> {_font('comment', f'{_fmt_day(today)} · Action 日报')}",
        "",
    ]
    if summary is not None:
        parts.extend(
            [
                "**📆 本期测试周期**",
                f"> {_fmt_dt(summary.week_start)} → {_fmt_dt(summary.week_end)}"
                f"（{summary.week_key}）",
                "",
                "**🔹 Action 速览**",
                (
                    f"> 汇报周 Action {_font('info', str(summary.action_count))}　"
                    f"今日日更 {_font('info', str(len(lines)))}　"
                    f"当前有风险 {_font('warning' if summary.risk_action_count else 'info', str(summary.risk_action_count))}"
                ),
                "",
            ]
        )

    action_parts, action_omitted = _format_daily_action_section(
        lines, max_lines=max_action_lines
    )
    parts.extend(action_parts)
    if action_omitted > 0:
        parts.append(
            _font("comment", f"另有 {action_omitted} 条今日 Action 未列出，详见大屏")
        )
        parts.append("")

    parts.append(
        (
            f"**⚠ 当前风险（Action）**  "
            f"{_font('warning', f'新增 {len(diff.added)}')}"
            f"　{_font('comment', f'未解决 {len(diff.unresolved)}')}"
            + (
                f"　{_font('info', f'已消除 {len(diff.resolved_ids)}')}"
                if diff.resolved_ids
                else ""
            )
        )
    )
    parts.append("")
    if added:
        parts.append(f"#### {_font('warning', '新增风险')}")
        parts.extend(_risk_block(r, index=i, tone="warning") for i, r in enumerate(added, 1))
        parts.append("")
    if unresolved:
        start_i = len(added) + 1
        parts.append(f"#### {_font('comment', '未解决风险')}")
        parts.extend(
            _risk_block(r, index=i, tone="comment")
            for i, r in enumerate(unresolved, start_i)
        )
        parts.append("")
    if not added and not unresolved:
        if len(diff.added) + len(diff.unresolved) == 0:
            parts.append(_font("info", "本日无开放风险（或均已消除）"))
        else:
            parts.append(_font("comment", "风险过多已省略明细，请打开项目管理大屏"))
        parts.append("")
    if risk_omitted > 0:
        parts.append(
            _font("comment", f"另有 {risk_omitted} 条风险未列出，详见大屏")
        )
        parts.append("")
    parts.append(_font("comment", "详情见项目管理 · 本周大屏（Action 视图）"))
    return "\n".join(parts).strip()


def build_weekly_markdown(
    *,
    summary: ProgressSummary,
    diff: RiskDiff,
    task_rows: list[TaskProgressRow] | None = None,
    max_risk_items: int = WECOM_PUSH_RISK_ITEMS_SOFT_MAX,
    max_task_rows: int = WECOM_WEEKLY_TASK_ROWS_SOFT_MAX,
) -> str:
    """
    周报：偏 Task。
    - 一行整体 KPI
    - Task 列表（风险嵌在每个 Task 下方，不再单独风险大节）
    max_risk_items：此处用作「每个 Task 最多展开几条风险」。
    """
    rows = list(task_rows or [])
    # 若行上无 Action 风险明细，用当前开放风险回填
    if rows and not any(r.risk_items for r in rows) and diff.current:
        by_tid: dict[str, list[OpenRisk]] = {}
        for rsk in diff.current.values():
            tid = (rsk.task_id or "").strip() or f"title:{rsk.domain_name}|{rsk.task_title}"
            by_tid.setdefault(tid, []).append(rsk)
        filled: list[TaskProgressRow] = []
        for r in rows:
            key = r.task_id or f"title:{r.domain_name}|{r.task_title}"
            items_src = by_tid.get(key) or by_tid.get(f"title:{r.domain_name}|{r.task_title}") or []
            if items_src and not r.risk_items:
                items = [
                    TaskRiskItem(
                        action_title=x.action_title,
                        risk=x.risk,
                        progress=x.progress,
                        owner_name=x.owner_name,
                    )
                    for x in items_src
                ]
                filled.append(
                    TaskProgressRow(
                        task_id=r.task_id,
                        task_title=r.task_title,
                        domain_name=r.domain_name,
                        project_name=r.project_name,
                        progress_avg=r.progress_avg,
                        action_count=r.action_count,
                        published_count=r.published_count,
                        done_count=r.done_count,
                        draft_count=r.draft_count,
                        risk_count=max(r.risk_count, len(items)),
                        risk_texts=[x.risk for x in items],
                        risk_items=items,
                    )
                )
            else:
                filled.append(r)
        rows = filled

    risk_task_n = sum(1 for r in rows if r.risk_count > 0)
    avg_color = _progress_tone(summary.progress_avg)
    risk_color = "warning" if risk_task_n > 0 else "info"

    parts: list[str] = [
        "### 📋 【测试周报】TestAI",
        f"> 🗓️ {_fmt_week_span(summary.week_start, summary.week_end)}",
        "",
        (
            f"Task {_font('info', str(summary.task_count))}　"
            f"Action {_font('info', str(summary.action_count))}　"
            f"均进度 {_font(avg_color, f'{summary.progress_avg}%')}　"
            f"风险 {_font(risk_color, str(risk_task_n))}"
        ),
        "",
    ]

    task_parts, task_omitted = _format_weekly_task_section(
        rows,
        max_rows=max_task_rows,
        max_risks_per_task=max(1, max_risk_items),
    )
    parts.extend(task_parts)
    if task_omitted > 0:
        parts.append(_font("comment", f"另有 {task_omitted} 个 Task 未列出，详见大屏"))
        parts.append("")
    parts.append(_font("comment", "详情见 TestAI · 项目管理"))
    return "\n".join(parts).strip()


def utf8_len(text: str) -> int:
    return len(text.encode("utf-8"))


def _hard_truncate(content: str, max_bytes: int) -> str:
    raw = content.encode("utf-8")
    if len(raw) <= max_bytes:
        return content
    suffix = "\n\n…(已截断，详见大屏)"
    budget = max_bytes - len(suffix.encode("utf-8"))
    if budget < 64:
        budget = max_bytes
        suffix = ""
    cut = raw[:budget]
    while cut and (cut[-1] & 0xC0) == 0x80:
        cut = cut[:-1]
    return cut.decode("utf-8", errors="ignore") + suffix


async def fit_daily_markdown(
    *,
    today: date,
    diff: RiskDiff,
    summary: ProgressSummary | None = None,
    action_lines: list[TodayActionLine] | None = None,
    max_bytes: int = WECOM_MSG_MAX_BYTES,
) -> str:
    """
    日报适配单条上限（禁止拆条，禁止依赖 AI）：
    1) 全文能塞下则全文；
    2) 超长则递减 Action/风险条数（确定性）；
    3) 仍超长则硬截断 —— 保证一定产出可发正文。
    """
    lines = action_lines or []
    full = build_daily_markdown(
        today=today,
        diff=diff,
        summary=summary,
        action_lines=lines,
        max_risk_items=WECOM_PUSH_RISK_ITEMS_SOFT_MAX,
        max_action_lines=max(len(lines), WECOM_DAILY_ACTION_LINES_SOFT_MAX),
    )
    if utf8_len(full) <= max_bytes:
        return full

    log.warning(
        "daily oversized (%s), shrink without AI (deterministic)", utf8_len(full)
    )
    for n_risk in range(WECOM_PUSH_RISK_ITEMS_SOFT_MAX, -1, -1):
        for n_act in range(WECOM_DAILY_ACTION_LINES_SOFT_MAX, -1, -1):
            md = build_daily_markdown(
                today=today,
                diff=diff,
                summary=summary,
                action_lines=lines,
                max_risk_items=n_risk,
                max_action_lines=n_act,
            )
            if utf8_len(md) <= max_bytes:
                return md

    md = build_daily_markdown(
        today=today,
        diff=diff,
        summary=summary,
        action_lines=lines,
        max_risk_items=0,
        max_action_lines=0,
    )
    if utf8_len(md) <= max_bytes:
        return md
    return _hard_truncate(md, max_bytes)


async def fit_weekly_markdown(
    *,
    summary: ProgressSummary,
    diff: RiskDiff,
    task_rows: list[TaskProgressRow] | None = None,
    max_bytes: int = WECOM_MSG_MAX_BYTES,
) -> str:
    """
    周报适配单条上限（禁止拆条，禁止依赖 AI）：
    递减 Task/风险行，最后硬截断，保证一定可发。
    """
    rows = task_rows or []
    full = build_weekly_markdown(
        summary=summary,
        diff=diff,
        task_rows=rows,
        max_risk_items=WECOM_PUSH_RISK_ITEMS_SOFT_MAX,
        max_task_rows=max(len(rows), WECOM_WEEKLY_TASK_ROWS_SOFT_MAX),
    )
    if utf8_len(full) <= max_bytes:
        return full

    log.warning(
        "weekly oversized (%s), shrink without AI (deterministic)", utf8_len(full)
    )
    for n_risk in range(WECOM_PUSH_RISK_ITEMS_SOFT_MAX, -1, -1):
        for n_task in range(WECOM_WEEKLY_TASK_ROWS_SOFT_MAX, -1, -1):
            md = build_weekly_markdown(
                summary=summary,
                diff=diff,
                task_rows=rows,
                max_risk_items=n_risk,
                max_task_rows=n_task,
            )
            if utf8_len(md) <= max_bytes:
                return md

    md = build_weekly_markdown(
        summary=summary,
        diff=diff,
        task_rows=rows,
        max_risk_items=0,
        max_task_rows=0,
    )
    if utf8_len(md) <= max_bytes:
        return md
    return _hard_truncate(md, max_bytes)


async def ensure_message_fits(content: str, *, max_bytes: int = WECOM_MSG_MAX_BYTES) -> str:
    """兼容旧调用：超长直接硬截断（不调 AI，避免拖死定时任务）。"""
    if utf8_len(content) <= max_bytes:
        return content
    return _hard_truncate(content, max_bytes)


def daily_period_key(today: date | None = None) -> str:
    d = today or now_tm().date()
    return d.isoformat()


def weekly_period_key(ws: datetime | None = None) -> str:
    return week_key(ws or current_week_start())


# 供外部区分 kind
REPORT_KINDS = (REPORT_KIND_DAILY, REPORT_KIND_WEEKLY)
