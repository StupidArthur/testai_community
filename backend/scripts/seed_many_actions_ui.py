"""
工作台 UI：同一 Task 下灌入多条 Action，便于看网格折行展示。

用法（backend 目录，无命令行参数）：
  python scripts/seed_many_actions_ui.py
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

try:
    from dotenv import load_dotenv

    load_dotenv(BACKEND_DIR / ".env")
    load_dotenv(BACKEND_DIR.parent / ".env")
except Exception:
    pass

# 可调参数（改这里，不要用命令行）
ACTION_COUNT = 10
PROJECT_NAME = "TPT v2.1"
TASK_TITLE = "【UI】多 Action 展示"
TASK_REQUIREMENT = "设备健康 / 报警管理 / 操作导引 / 网络优化 / 智能控制（UI 多卡展示）"
MARKER = "seed_many_actions_ui"

_ACTION_SPECS = [
    ("设备健康巡检", 90, "data-hub link 数据未上送"),
    ("报警管理联调", 85, "数据读写问题尚未解决"),
    ("操作导引验收", 70, ""),
    ("网络优化回归", 60, "弱网场景偶发超时"),
    ("智能控制用例", 55, ""),
    ("边云协同冒烟", 40, "边缘节点证书过期"),
    ("权限矩阵核对", 95, ""),
    ("报表导出验证", 30, ""),
    ("性能基线采集", 20, "压测环境排队中"),
    ("文档与交付检查", 10, ""),
    ("补充用例 A", 50, ""),
    ("补充用例 B", 45, "依赖上游接口未就绪"),
]


def seed_many_actions_ui(
    *,
    action_count: int = ACTION_COUNT,
    project_name: str = PROJECT_NAME,
    task_title: str = TASK_TITLE,
) -> dict:
    """在本周窗口下，为目标 Task 写入 action_count 条已发布 Action。"""
    from app.auth.models import User, UserRole
    from app.platform.database import Base, SessionLocal, engine
    from app.test_manage import models as _models  # noqa: F401
    from app.test_manage.config import STATUS_PUBLISHED, TASK_STATUS_PUBLISHED, now_tm
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
    n = max(1, int(action_count))
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

        owners = (
            db.query(User)
            .filter(User.role.in_([UserRole.Engineer, UserRole.Manager, UserRole.Admin]))
            .filter(User.username != "无")
            .order_by(User.id.asc())
            .limit(16)
            .all()
        )
        if not owners:
            owners = [admin]

        proj = db.query(TmProject).filter(TmProject.name == project_name).first()
        if not proj:
            raise RuntimeError(f"未找到项目 {project_name}，请先灌真实看板数据")

        domain = (
            db.query(TmDomain)
            .filter(TmDomain.project_id == proj.id)
            .order_by(TmDomain.name.asc())
            .first()
        )
        if not domain:
            raise RuntimeError("项目下无领域")

        period = get_or_create_active_period(db)
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
                    summary="UI 多 Action 展示灌数",
                    detail=MARKER,
                )
            )
        else:
            task.requirement = TASK_REQUIREMENT
            task.status = TASK_STATUS_PUBLISHED
            task.domain_id = domain.id

        # 清掉本 Task 本周旧 mock Action（含日更）
        old_ids = [
            a.id
            for a in db.query(TmAction)
            .filter(
                TmAction.task_id == task.id,
                TmAction.week_key == period.week_key,
            )
            .all()
        ]
        if old_ids:
            db.query(TmDailyUpdate).filter(TmDailyUpdate.action_id.in_(old_ids)).delete(
                synchronize_session=False
            )
            db.query(TmAction).filter(TmAction.id.in_(old_ids)).delete(synchronize_session=False)
            db.flush()

        created = []
        for i in range(n):
            title_base, progress, risk = _ACTION_SPECS[i % len(_ACTION_SPECS)]
            if i >= len(_ACTION_SPECS):
                title_base = f"{title_base}-{i + 1}"
            owner = owners[i % len(owners)]
            action = TmAction(
                task_id=task.id,
                project_id=proj.id,
                domain_id=domain.id,
                week_start=period.week_start,
                week_key=period.week_key,
                title=f"{title_base}"[:200],
                owner_id=owner.id,
                test_content=f"{MARKER} · {title_base}"[:1000],
                environment="qa",
                status=STATUS_PUBLISHED,
                created_by=admin.id,
                published_at=now_tm(),
                due_at=period.week_end,
            )
            db.add(action)
            db.flush()
            db.add(
                TmDailyUpdate(
                    action_id=action.id,
                    user_id=owner.id,
                    report_date=now_tm().date(),
                    progress_percent=int(progress),
                    progress_note=f"UI mock 日更 · {title_base}",
                    risk_blocker=(risk or "").strip(),
                )
            )
            created.append({"id": action.id, "title": action.title, "progress": progress, "risk": bool(risk)})

        db.commit()
        info = {
            "project": proj.name,
            "task_id": task.id,
            "task_title": task.title,
            "week_key": period.week_key,
            "action_count": len(created),
            "actions": created,
        }
        print(
            f"== done: project={info['project']} task={info['task_title']} "
            f"week={info['week_key']} actions={info['action_count']}"
        )
        print("  工作台筛选项目「TPT v2.1」，找 Task「【UI】多 Action 展示」即可。")
        return info
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_many_actions_ui(action_count=ACTION_COUNT)
