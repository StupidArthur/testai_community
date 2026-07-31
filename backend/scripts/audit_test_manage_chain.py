"""
整链审计：灌数表 → DB → service → 推送数据一致性 + 已知可疑边界。

在 backend 目录对 database_dev 执行：
    python scripts/audit_test_manage_chain.py

结果打印 BUG / WARN / OK，exit 1 若有 BUG。
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from sqlalchemy.orm import joinedload

from app.auth.models import User
from app.platform.database import SessionLocal
from app.test_manage.config import STATUS_CANCELLED, STATUS_DRAFT, STATUS_PUBLISHED, STATUS_DONE
from app.test_manage.models import TmAction, TmDailyUpdate, TmProject, TmTask, TmTaskTester
from app.test_manage.push_report import collect_open_risks, collect_progress_summary, _latest_progress
from app.test_manage.service import (
    _action_owner_candidate_ids,
    get_board,
    list_assignable_users,
    list_mine_actions,
)
from app.test_manage.week import current_week_start, week_key

PROJECT_NAME = "TPT v2.1"


class Report:
    def __init__(self) -> None:
        self.bugs: list[str] = []
        self.warns: list[str] = []
        self.oks: list[str] = []

    def bug(self, msg: str) -> None:
        self.bugs.append(msg)
        print(f"[BUG]  {msg}")

    def warn(self, msg: str) -> None:
        self.warns.append(msg)
        print(f"[WARN] {msg}")

    def ok(self, msg: str) -> None:
        self.oks.append(msg)
        print(f"[OK]   {msg}")


def audit() -> int:
    r = Report()
    db = SessionLocal()
    try:
        project = db.query(TmProject).filter(TmProject.name == PROJECT_NAME).first()
        if not project:
            r.bug(f"缺少项目 {PROJECT_NAME}，请先 seed")
            return 1

        tasks = (
            db.query(TmTask)
            .options(joinedload(TmTask.testers), joinedload(TmTask.domain))
            .filter(TmTask.project_id == project.id)
            .all()
        )
        actions = (
            db.query(TmAction)
            .options(joinedload(TmAction.daily_updates))
            .filter(TmAction.project_id == project.id)
            .all()
        )
        r.ok(f"项目 {PROJECT_NAME}: tasks={len(tasks)} actions={len(actions)}")

        # ── A1：所有 Action owner ∈ Task 参与者 ──
        a1_bad = []
        for a in actions:
            task = next((t for t in tasks if t.id == a.task_id), None)
            if not task:
                a1_bad.append(f"{a.title}: 无 Task")
                continue
            cands = _action_owner_candidate_ids(task)
            if a.owner_id not in cands:
                owner = db.query(User).filter(User.id == a.owner_id).first()
                a1_bad.append(
                    f"{a.title} week={a.week_key} owner={owner.username if owner else a.owner_id}"
                )
        if a1_bad:
            r.bug(f"A1 违规 {len(a1_bad)} 条: " + "; ".join(a1_bad[:5]))
        else:
            r.ok("全部 Action 满足 A1（owner ∈ lead∪testers）")

        # ── 占位账号「无」不应再被用作已发布 Action owner ──
        wu = db.query(User).filter(User.username == "无").first()
        if wu:
            owned = [a for a in actions if a.owner_id == wu.id and a.status != STATUS_CANCELLED]
            if owned:
                r.bug(
                    f"非取消 Action 仍挂在占位账号「无」上: "
                    + ", ".join(f"{a.title}({a.status})" for a in owned[:5])
                )
            else:
                r.ok("非取消 Action 未挂占位账号「无」")

        # ── cancelled 仅本周（或不应有多周噪音）──
        wk = week_key(current_week_start())
        cancelled = [a for a in actions if a.status == STATUS_CANCELLED]
        old_cancelled = [a for a in cancelled if a.week_key != wk]
        if old_cancelled:
            r.warn(
                f"存在非本周 cancelled Action {len(old_cancelled)} 条（预期灌数仅本周）"
            )
        else:
            r.ok(f"cancelled Action 均在本周（n={len(cancelled)}）")

        # ── 日更 user 应是 owner 或管理员写的？seed 用 owner ──
        bad_daily_user = []
        for a in actions:
            for u in a.daily_updates or []:
                if u.user_id != a.owner_id:
                    bad_daily_user.append(a.title)
                    break
        if bad_daily_user:
            r.warn(
                f"{len(bad_daily_user)} 个 Action 日更作者≠当前 owner（改派后历史正常）: "
                + ", ".join(bad_daily_user[:3])
            )
        else:
            r.ok("日更 user_id 均等于当前 owner_id")

        # ── 风险「已解决」语义：最新日更为空风险，但 _latest_progress 仍返回旧风险？──
        stale_risk = []
        for a in actions:
            updates = list(a.daily_updates or [])
            if len(updates) < 2:
                continue

            def _sk(u: TmDailyUpdate):
                return (u.report_date, u.updated_at or u.created_at)

            latest = max(updates, key=_sk)
            _p, shown_risk = _latest_progress(a)
            latest_risk = (latest.risk_blocker or "").strip()
            if not latest_risk and (shown_risk or "").strip():
                stale_risk.append(
                    f"{a.title}: 最新日更已清空风险，但展示仍为「{(shown_risk or '')[:40]}」"
                )
        if stale_risk:
            r.bug(
                f"风险已解决语义错误（最新日更清空后仍显示旧风险）{len(stale_risk)}: "
                + "; ".join(stale_risk[:3])
            )
        else:
            # 构造场景验证逻辑
            r.ok("灌数数据中未触发「清空风险仍显示」；另见单测验证逻辑")

        # ── board published_count 仅计 published（与周报一致）──
        admin = db.query(User).filter(User.username == "admin").first()
        board = get_board(db, admin, project_id=project.id)
        done_n = sum(
            1
            for bt in board.tasks
            for a in bt.actions
            if a.status == STATUS_DONE
        )
        pub_only = sum(
            1
            for bt in board.tasks
            for a in bt.actions
            if a.status == STATUS_PUBLISHED
        )
        if board.summary.published_count != pub_only:
            r.bug(
                f"看板 published_count={board.summary.published_count} "
                f"应等于 published 数 {pub_only}"
            )
        elif getattr(board.summary, "done_count", None) != done_n:
            r.bug(
                f"看板 done_count={getattr(board.summary, 'done_count', None)} "
                f"应等于 {done_n}"
            )
        else:
            r.ok(
                f"看板 published={board.summary.published_count} "
                f"done={board.summary.done_count}（口径正确）"
            )

        # ── 推送开放风险 vs 看板 latest_risk ──
        open_risks = collect_open_risks(db)
        board_risk_ids = {
            a.id
            for bt in board.tasks
            for a in bt.actions
            if (a.latest_risk or "").strip()
        }
        # 推送可能含其他项目；只比本项目
        proj_open = {aid for aid, risk in open_risks.items() if aid in {a.id for a in actions}}
        if proj_open != board_risk_ids:
            only_push = proj_open - board_risk_ids
            only_board = board_risk_ids - proj_open
            r.bug(
                f"推送开放风险与看板不一致: only_push={len(only_push)} only_board={len(only_board)}"
            )
        else:
            r.ok(f"本项目推送开放风险与看板一致 n={len(proj_open)}")

        # ── 周报 published_count 与看板对齐 ──
        summary = collect_progress_summary(db)
        if summary.published_count != board.summary.published_count:
            r.bug(
                f"周报 published_count={summary.published_count} ≠ 看板 "
                f"{board.summary.published_count}"
            )
        else:
            r.ok(
                f"周报/看板 published 一致={summary.published_count}；"
                f"周报 done={summary.done_count}"
            )

        # ── 工程师视角：只能看到参与的 ──
        hj = db.query(User).filter(User.username == "hj").first()
        if hj:
            board_hj = get_board(db, hj, project_id=project.id)
            for bt in board_hj.tasks:
                if not bt.actions and bt.task.lead_id != hj.id and hj.id not in bt.task.tester_ids:
                    r.bug(f"工程师 hj 看到无关空 Task: {bt.task.title}")
            mine = list_mine_actions(db, hj)
            for a in mine:
                if a.owner_id != hj.id:
                    r.bug(f"mine 出现非本人 Action: {a.title}")
                if a.week_key != wk:
                    r.bug(f"mine 出现非本周: {a.title} {a.week_key}")
            r.ok(
                f"工程师 hj: board_tasks={len(board_hj.tasks)} mine={len(mine)} "
                f"(admin board_tasks={len(board.tasks)})"
            )

        # ── assignable users 不含「无」──
        users = list_assignable_users(db, admin)
        if any(u.username == "无" for u in users):
            r.bug("可指派用户列表仍含「无」")
        else:
            r.ok(f"可指派用户排除「无」，共 {len(users)} 人")

        # ── 本周 Action 标题重复（合并灌数是否意外翻倍）──
        titles = defaultdict(list)
        for a in actions:
            if a.week_key == wk:
                titles[a.title].append(a.id)
        dups = {t: ids for t, ids in titles.items() if len(ids) > 1}
        if dups:
            r.warn(f"本周同标题多条 Action {len(dups)} 组: " + ", ".join(list(dups)[:5]))
        else:
            r.ok("本周无同标题重复 Action")

        # ── draft 无日更进度应为 0 ──
        drafts = [a for a in actions if a.status == STATUS_DRAFT and a.week_key == wk]
        for a in drafts:
            p, risk = _latest_progress(a)
            if p != 0 and not a.daily_updates:
                r.bug(f"草稿 {a.title} 无日更但进度={p}")
        r.ok(f"本周草稿数={len(drafts)}")

        print("\n======== SUMMARY ========")
        print(f"OK={len(r.oks)} WARN={len(r.warns)} BUG={len(r.bugs)}")
        return 1 if r.bugs else 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(audit())
