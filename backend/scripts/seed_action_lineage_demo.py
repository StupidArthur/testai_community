"""
在目标库造「Action 延续历史」演示数据（共 2 周）。

用法：在目标机 backend 目录执行（无命令行参数）：
  .\\.venv\\Scripts\\python.exe scripts\\seed_action_lineage_demo.py

会：
1) 建项目【演示】Action延续历史（若已存在同名则复用）
2) 建 Task + 上周 Action（含日更与风险）
3) 克隆为本周 Action（无风险文案）
4) 打印：到工作台筛选该项目，打开「本周」那条 Action → 延续历史（共 2 周）
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

DEMO_PROJECT_NAME = "【演示】Action延续历史"
DEMO_DOMAIN_NAME = "演示领域"
DEMO_TASK_TITLE = "【演示】跨周延续 Task"
DEMO_ACTION_TITLE = "【演示】延续-跨周条目"


def seed_action_lineage_demo(
    *,
    project_name: str = DEMO_PROJECT_NAME,
) -> dict:
    """写入演示数据并返回 id 字典。"""
    from app.auth.models import User, UserRole
    from app.platform.database import Base, SessionLocal, engine
    from app.test_manage import models as _models  # noqa: F401
    from app.test_manage.config import now_tm
    from app.test_manage.models import TmAction, TmDomain, TmProject, TmTask, TmWeekPeriod
    from app.test_manage.period import get_or_create_active_period
    from app.test_manage.schemas import (
        ActionCloneRequest,
        ActionCreate,
        DailyUpdateUpsert,
        DomainCreate,
        ProjectCreate,
        TaskCreate,
    )
    from app.test_manage.service import (
        clone_action,
        create_action,
        create_domain,
        create_project,
        create_task,
        upsert_daily_update,
    )
    from app.test_manage.week import week_key

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
            raise RuntimeError("未找到 Admin/Manager 用户")

        proj = (
            db.query(TmProject)
            .filter(TmProject.name == project_name, TmProject.status == "active")
            .first()
        )
        if not proj:
            pout = create_project(
                db, admin, ProjectCreate(name=project_name, description="验收延续历史用")
            )
            proj = db.query(TmProject).filter(TmProject.id == pout.id).one()

        dom = (
            db.query(TmDomain)
            .filter(TmDomain.project_id == proj.id, TmDomain.name == DEMO_DOMAIN_NAME)
            .first()
        )
        if not dom:
            dout = create_domain(
                db, admin, proj.id, DomainCreate(name=DEMO_DOMAIN_NAME)
            )
            dom = db.query(TmDomain).filter(TmDomain.id == dout.id).one()

        task_row = (
            db.query(TmTask)
            .filter(TmTask.project_id == proj.id, TmTask.title == DEMO_TASK_TITLE)
            .first()
        )
        if not task_row:
            tout = create_task(
                db,
                admin,
                TaskCreate(
                    project_id=proj.id,
                    domain_id=dom.id,
                    title=DEMO_TASK_TITLE,
                    requirement="演示 Action 跨周延续；测完可归档本项目",
                    lead_id=admin.id,
                    tester_ids=[admin.id],
                    publish=True,
                ),
            )
            task_id = tout.id
        else:
            task_id = task_row.id

        period = get_or_create_active_period(db)
        prev_period = (
            db.query(TmWeekPeriod)
            .filter(TmWeekPeriod.week_end <= period.week_start)
            .order_by(TmWeekPeriod.week_end.desc())
            .first()
        )
        # 清理本演示 Task 下旧演示 Action，避免重复
        olds = (
            db.query(TmAction)
            .filter(
                TmAction.task_id == task_id,
                TmAction.title.like("【演示】延续%"),
            )
            .all()
        )
        for a in olds:
            a.source_action_id = None
        db.flush()
        for a in olds:
            db.delete(a)
        db.flush()

        w1 = create_action(
            db,
            admin,
            ActionCreate(
                task_id=task_id,
                title=DEMO_ACTION_TITLE,
                owner_id=admin.id,
                test_content="第一周：搭环境并完成冒烟",
                environment="演示环境",
                publish=True,
            ),
        )

        # 先写日更（尚在当前周，避免切周后日更周不一致）
        upsert_daily_update(
            db,
            admin,
            w1.id,
            DailyUpdateUpsert(
                progress_percent=40,
                progress_note="第一周：环境已通，冒烟 3 条过",
                risk_blocker="压测机资源不足（演示风险）",
            ),
        )

        # 再挪到上一业务周，模拟「上周已发生」的 Action
        row = db.query(TmAction).filter(TmAction.id == w1.id).one()
        if prev_period:
            row.week_start = prev_period.week_start
            row.week_key = prev_period.week_key
            row.due_at = prev_period.week_end
        else:
            prev_start = row.week_start - timedelta(days=7)
            row.week_start = prev_start
            row.week_key = week_key(prev_start)
            row.due_at = prev_start + timedelta(days=7)
        db.commit()

        cloned = clone_action(
            db, admin, w1.id, ActionCloneRequest(publish=True, title=DEMO_ACTION_TITLE)
        )

        from app.test_manage.service import get_action_lineage

        lin = get_action_lineage(db, admin, cloned.id)
        return {
            "project_id": proj.id,
            "project_name": proj.name,
            "task_id": task_id,
            "prev_action_id": w1.id,
            "current_action_id": cloned.id,
            "active_week_key": period.week_key,
            "weeks_count": lin.weeks_count,
            "segments": [
                {
                    "week_key": s.week_key,
                    "title": s.title,
                    "progress": s.progress_percent,
                    "risks": s.risks,
                    "is_current": s.is_current,
                }
                for s in lin.segments
            ],
        }
    finally:
        db.close()


if __name__ == "__main__":
    info = seed_action_lineage_demo()
    print("== lineage demo ready ==")
    for k, v in info.items():
        if k == "segments":
            print("segments:")
            for s in v:
                print(" ", s)
        else:
            print(f"{k}={v}")
    print()
    print("如何看：")
    print("1) 打开 http://生产地址/projects → 工作台")
    print(f"2) 项目筛到：{info['project_name']}")
    print("3) 打开 Task「【演示】跨周延续 Task」下「本周」那条已发布 Action")
    print("4) 抽屉里展开「延续历史（共 2 周）」")
    print("   - 上周片段有风险「压测机资源不足」")
    print("   - 本周片段有进度、风险应为空（克隆不带风险）")
