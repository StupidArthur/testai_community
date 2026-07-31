"""
清理开发库自动化测试残留：【E2E】/【回归】/【切周】业务数据，以及 e2e*、tm_live_* 账号。

用法（在 backend 目录）：
  python scripts/cleanup_tm_test_data.py
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from sqlalchemy import or_

from app.auth.models import User
from app.platform.database import SessionLocal
from app.test_manage.models import TmAction, TmDomain, TmProject, TmTask

# 标题 / 项目名 / 领域名前缀
NAME_PREFIXES = ("【E2E】", "【回归】", "【回归+】", "【切周】", "【测试】", "【UI测试】")
# 用户名：e2eL_ / e2eO_ / e2eT_ / e2eX_ / e2e… 以及现场回归账号
USER_PREFIXES = ("e2e", "tm_live_")


def _like_any(column, prefixes: tuple[str, ...]):
    return or_(*[column.like(f"{p}%") for p in prefixes])


def cleanup_tm_test_data() -> dict[str, int]:
    """删除测试前缀业务数据与测试账号；返回删除计数。"""
    db = SessionLocal()
    counts = {
        "projects": 0,
        "domains": 0,
        "tasks": 0,
        "actions": 0,
        "users": 0,
    }
    try:
        # 1) E2E 等独立项目（级联领域 / Task / Action）
        projects = (
            db.query(TmProject).filter(_like_any(TmProject.name, NAME_PREFIXES)).all()
        )
        counts["projects"] = len(projects)
        for p in projects:
            db.delete(p)
        db.flush()

        # 2) 挂在真实项目（如 TPT）上的回归 Task
        tasks = db.query(TmTask).filter(_like_any(TmTask.title, NAME_PREFIXES)).all()
        counts["tasks"] = len(tasks)
        for t in tasks:
            db.delete(t)
        db.flush()

        # 3) 残留 Action / 领域
        actions = (
            db.query(TmAction).filter(_like_any(TmAction.title, NAME_PREFIXES)).all()
        )
        # 先清自引用，避免删不全
        for a in actions:
            a.source_action_id = None
        db.flush()
        counts["actions"] = len(actions)
        for a in actions:
            db.delete(a)
        db.flush()

        domains = (
            db.query(TmDomain).filter(_like_any(TmDomain.name, NAME_PREFIXES)).all()
        )
        counts["domains"] = len(domains)
        for d in domains:
            db.delete(d)
        db.flush()

        # 4) 测试账号
        users = (
            db.query(User)
            .filter(or_(*[User.username.like(f"{p}%") for p in USER_PREFIXES]))
            .all()
        )
        counts["users"] = len(users)
        for u in users:
            db.delete(u)

        db.commit()
        return counts
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    result = cleanup_tm_test_data()
    print("cleanup_tm_test_data done:", result)
