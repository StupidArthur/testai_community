"""
大屏筛选矩阵 mock：有/无阻塞 × 有/无今日日更（4 条 Action）。

口径说明：
- 「有阻塞」看最新一条日更：risk 有文案且 is_blocking=True
- 「今日日更」只看今天是否有日更记录
- 因此「阻塞 + 未日更」= 昨天日更勾了阻塞，今天还没再写日更

用法（backend 目录，无命令行参数）：
  python scripts/seed_filter_matrix_demo.py
"""
from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

try:
    from dotenv import load_dotenv

    load_dotenv(BACKEND_DIR / ".env")
    load_dotenv(BACKEND_DIR.parent / ".env")
except Exception:
    pass

# 可调参数（改这里）
PROJECT_NAME = "TPT v2.1"
TASK_TITLE = "【筛测】阻塞×日更矩阵"
TASK_REQUIREMENT = "筛选自测：有阻塞/无阻塞 × 已日更/未日更"
MARKER = "seed_filter_matrix_demo"

# title, progress, risk, is_blocking, daily_on: "today" | "yesterday" | "none"
_SPECS: list[tuple[str, int, str, bool, str]] = [
    ("【筛测A】阻塞+已日更", 40, "【筛测】环境不可用（应出现在：有阻塞）", True, "today"),
    ("【筛测B】阻塞+未日更", 35, "【筛测】阻塞且今日未日更（默认筛应只剩这条同类）", True, "yesterday"),
    ("【筛测C】有风险无阻塞+已日更", 50, "【筛测】有风险但未勾阻塞（应出现在：有风险，不应进有阻塞）", False, "today"),
    ("【筛测D】无风险+未日更", 20, "", False, "yesterday"),
]


def seed_filter_matrix_demo(
    *,
    project_name: str = PROJECT_NAME,
    task_title: str = TASK_TITLE,
) -> dict:
    """写入/刷新筛选矩阵 4 条 Action，便于大屏试筛。"""
    from app.auth.models import User, UserRole
    from app.platform.database import Base, SessionLocal, engine
    from app.test_manage import models as _models  # noqa: F401
    from app.test_manage.config import STATUS_PUBLISHED, TASK_STATUS_PUBLISHED, now_tm, today_tm
    from app.test_manage.models import (
        TmAction,
        TmDailyUpdate,
        TmDomain,
        TmProject,
        TmTask,
        TmTaskUpdateLog,
    )
    from app.test_manage.period import get_or_create_active_period

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        admin = (
            db.query(User)
            .filter(User.role.in_([UserRole.Admin, UserRole.Manager]))
            .order_by(User.id.asc())
            .first()
        )
        if not admin:
            raise RuntimeError("未找到 Admin/Manager")

        proj = db.query(TmProject).filter(TmProject.name == project_name).first()
        if not proj:
            raise RuntimeError(f"未找到项目 {project_name}")

        domain = (
            db.query(TmDomain)
            .filter(TmDomain.project_id == proj.id)
            .order_by(TmDomain.name.asc())
            .first()
        )
        if not domain:
            raise RuntimeError("项目下无领域")

        period = get_or_create_active_period(db)
        today = today_tm()
        yesterday = today - timedelta(days=1)

        task = (
            db.query(TmTask)
            .filter(TmTask.project_id == proj.id, TmTask.title == task_title)
            .first()
        )
        if not task:
            task = TmTask(
                project_id=proj.id,
                domain_id=domain.id,
                title=task_title,
                requirement=TASK_REQUIREMENT,
                lead_id=admin.id,
                status=TASK_STATUS_PUBLISHED,
                created_by=admin.id,
                published_at=now_tm(),
            )
            db.add(task)
            db.flush()
            db.add(
                TmTaskUpdateLog(
                    task_id=task.id,
                    user_id=admin.id,
                    summary="筛选矩阵灌数",
                    detail=MARKER,
                )
            )
        else:
            task.requirement = TASK_REQUIREMENT
            task.status = TASK_STATUS_PUBLISHED
            task.domain_id = domain.id

        old_ids = [
            a.id
            for a in db.query(TmAction)
            .filter(TmAction.task_id == task.id, TmAction.week_key == period.week_key)
            .all()
        ]
        if old_ids:
            db.query(TmDailyUpdate).filter(TmDailyUpdate.action_id.in_(old_ids)).delete(
                synchronize_session=False
            )
            db.query(TmAction).filter(TmAction.id.in_(old_ids)).delete(synchronize_session=False)
            db.flush()

        created: list[dict] = []
        for title, progress, risk, is_blocking, daily_on in _SPECS:
            action = TmAction(
                task_id=task.id,
                project_id=proj.id,
                domain_id=domain.id,
                week_start=period.week_start,
                week_key=period.week_key,
                title=title[:200],
                owner_id=admin.id,
                test_content=f"{MARKER} · {title}"[:1000],
                environment="qa-filter-matrix",
                status=STATUS_PUBLISHED,
                created_by=admin.id,
                published_at=now_tm(),
                due_at=period.week_end,
            )
            db.add(action)
            db.flush()

            report_date = None
            if daily_on == "today":
                report_date = today
            elif daily_on == "yesterday":
                report_date = yesterday

            if report_date is not None:
                risk_txt = (risk or "").strip()
                db.add(
                    TmDailyUpdate(
                        action_id=action.id,
                        user_id=admin.id,
                        report_date=report_date,
                        progress_percent=int(progress),
                        progress_note=f"{MARKER} · {daily_on}",
                        risk_blocker=risk_txt,
                        is_blocking=bool(is_blocking) and bool(risk_txt),
                    )
                )

            created.append(
                {
                    "title": title,
                    "blocking": bool(is_blocking) and bool((risk or "").strip()),
                    "daily_today": daily_on == "today",
                    "expect": {
                        "有阻塞": bool(is_blocking) and bool((risk or "").strip()),
                        "未日更": daily_on != "today",
                        "已日更": daily_on == "today",
                        "有风险": bool((risk or "").strip()),
                    },
                }
            )

        db.commit()
        info = {
            "project": proj.name,
            "project_id": proj.id,
            "task_title": task_title,
            "week_key": period.week_key,
            "today": str(today),
            "actions": created,
        }
        print("== seed_filter_matrix_demo ==")
        print(f"project={info['project']} week={info['week_key']} today={info['today']}")
        print(f"task={info['task_title']}")
        for row in created:
            print(
                f"  - {row['title']} | blocking={row['blocking']} "
                f"daily_today={row['daily_today']}"
            )
        print()
        print("试筛预期（今日 Tab，项目选 TPT v2.1）：")
        print("  默认(进行中+有阻塞+未日更) → 只见【筛测B】")
        print("  有阻塞 + 日更=全部     → 【筛测A】【筛测B】")
        print("  有阻塞 + 已日更         → 只见【筛测A】")
        print("  阻塞=全部 + 未日更      → 【筛测B】【筛测D】（及库内其它未日更）")
        print("  风险=有风险 + 阻塞=全部 → 【筛测A】【筛测B】【筛测C】")
        return info
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_filter_matrix_demo()
