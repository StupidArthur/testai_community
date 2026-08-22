"""
灌入「多 Task + 少量阻塞 Action」演示/轻量压测数据。

默认贴近日常：3 Task × 2 Action、约 4 条阻塞；只清理标题含【压测】的旧数据。
若要极限压长度，可把 action_count / BLOCKER_ACTION_MAX 调大。

用法（backend 目录）：

    python scripts/seed_daily_stress_long.py
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

try:
    from dotenv import load_dotenv

    load_dotenv(_BACKEND.parent / ".env")
    load_dotenv(_BACKEND / ".env")
except Exception:
    pass

from sqlalchemy.orm import Session

from app.auth.models import User, UserRole
from app.platform.database import SessionLocal
from app.test_manage.config import STATUS_PUBLISHED, TASK_STATUS_PUBLISHED, now_tm
from app.test_manage.models import (
    TmAction,
    TmActionCorrection,
    TmDailyUpdate,
    TmDomain,
    TmProject,
    TmTask,
    TmTaskTester,
    TmTaskUpdateLog,
    TmTaskWeekProgress,
)
from app.test_manage.period import get_daily_context_period

PROJECT_NAME = "TPT v2.1"
STRESS_PREFIX = "【压测】"
# 兼容旧单 Task 标题常量
STRESS_TASK_TITLE = "【压测】日报长文案与多风险专项"

# 默认贴近日常观感：3 Task × 2 Action，阻塞约 3～5 条（不再灌 20+ 条）
TASK_COUNT = 3
ACTION_COUNT_PER_TASK = 2
# 带阻塞说明的 Action 上限（落在 3～5）
BLOCKER_ACTION_MAX = 4

# 说明/阻塞文案：够读、带一点长度，但不故意撑爆 4096
_LONG_NOTE_TEMPLATE = (
    "今日围绕「{topic}」完成联调与回归：核对用例矩阵与环境基线，"
    "复现历史缺陷并补边界组合（空值/超时/并发），与开发对齐后二次验证；"
    "用例 TC-{i:03d}～TC-{i2:03d} 已执行，明日补跨环境冒烟。"
)

_LONG_RISK_TEMPLATE = (
    "{topic}：环境不稳定间歇超时，疑下游限流+连接池耗尽；"
    "影响本周提测窗口，临时降并发并加熔断；待运维扩容与开发补丁（约 1～2 日）。"
)

# (领域名偏好, Task 标题后缀)
_STRESS_TASKS = (
    ("平台", "日报长文案与多风险专项"),
    ("Agent", "周报超长风险聚合专项"),
    ("交付", "跨领域长说明压缩专项"),
)

_TOPICS = (
    "Agent 编排链路",
    "知识库检索召回",
    "OPC UA 下写闭环",
    "大屏算法回归",
    "问数自然语言解析",
    "HMI 交互超时",
    "国际化文案覆盖",
    "数据查询三期",
    "长期稳定性压测",
    "权限矩阵边界",
    "配置中心热更新",
    "镜像发布回滚",
    "日志采集延迟",
    "告警收敛策略",
    "跨周延续克隆",
    "日更锁定窗口",
    "钉钉推送幂等",
    "周报 Task 聚合",
    "风险消除口径",
    "测试数据清洗",
    "向量库增量同步",
    "模型切换灰度",
    "并发会话隔离",
    "导出报表字段",
)


def _wipe_stress_only(db: Session, project_id: str) -> None:
    """只清标题带【压测】的 Task/Action，保留其它演示数据。"""
    tasks = (
        db.query(TmTask)
        .filter(TmTask.project_id == project_id, TmTask.title.like(f"{STRESS_PREFIX}%"))
        .all()
    )
    tids = [t.id for t in tasks]
    actions = (
        db.query(TmAction)
        .filter(TmAction.project_id == project_id, TmAction.title.like(f"{STRESS_PREFIX}%"))
        .all()
    )
    if tids:
        extra = db.query(TmAction).filter(TmAction.task_id.in_(tids)).all()
        seen = {a.id for a in actions}
        for a in extra:
            if a.id not in seen:
                actions.append(a)
    aids = [a.id for a in actions]
    if aids:
        db.query(TmDailyUpdate).filter(TmDailyUpdate.action_id.in_(aids)).delete(
            synchronize_session=False
        )
        db.query(TmActionCorrection).filter(TmActionCorrection.action_id.in_(aids)).delete(
            synchronize_session=False
        )
        db.query(TmAction).filter(TmAction.id.in_(aids)).update(
            {TmAction.source_action_id: None}, synchronize_session=False
        )
        db.query(TmAction).filter(TmAction.id.in_(aids)).delete(synchronize_session=False)
    if tids:
        db.query(TmTaskWeekProgress).filter(TmTaskWeekProgress.task_id.in_(tids)).delete(
            synchronize_session=False
        )
        db.query(TmTaskUpdateLog).filter(TmTaskUpdateLog.task_id.in_(tids)).delete(
            synchronize_session=False
        )
        db.query(TmTaskTester).filter(TmTaskTester.task_id.in_(tids)).delete(
            synchronize_session=False
        )
        db.query(TmTask).filter(TmTask.id.in_(tids)).delete(synchronize_session=False)
    print(f"  wiped stress tasks={len(tids)} actions={len(aids)}")


def _pick_domain(db: Session, project_id: str, preferred_name: str) -> TmDomain:
    """按偏好领域名取 domain，找不到则回退项目下任一领域。"""
    domain = (
        db.query(TmDomain)
        .filter(TmDomain.project_id == project_id, TmDomain.name == preferred_name)
        .first()
    )
    if domain:
        return domain
    domain = db.query(TmDomain).filter(TmDomain.project_id == project_id).first()
    if not domain:
        raise RuntimeError("项目下无领域")
    return domain


def seed_daily_stress_long(
    *,
    today: date | None = None,
    task_count: int = TASK_COUNT,
    action_count: int = ACTION_COUNT_PER_TASK,
) -> None:
    """
    写入多 Task 压测长文案日更。

    task_count：压测 Task 数（默认 3）；action_count：每 Task Action 数。
    today：日更日期，默认 now_tm().date()。
    """
    db = SessionLocal()
    try:
        print("== seed daily/weekly stress long ==")
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
            .order_by(User.id.asc())
            .limit(12)
            .all()
        )
        if not owners:
            owners = [admin]

        proj = db.query(TmProject).filter(TmProject.name == PROJECT_NAME).first()
        if not proj:
            raise RuntimeError(f"未找到项目 {PROJECT_NAME}，请先跑 seed_tpt_realistic_board.py")

        period = get_daily_context_period(db)
        report_day = today or now_tm().date()
        n_tasks = max(1, int(task_count))
        n_actions = max(1, int(action_count))
        print(
            f"  project={proj.name} week={period.week_key} "
            f"today={report_day} tasks={n_tasks} actions_per_task={n_actions}"
        )

        _wipe_stress_only(db, proj.id)
        db.flush()

        total_actions = 0
        total_risks = 0
        topic_cursor = 0

        for t_idx in range(n_tasks):
            pref_domain, title_suffix = _STRESS_TASKS[t_idx % len(_STRESS_TASKS)]
            domain = _pick_domain(db, proj.id, pref_domain)
            task_title = f"{STRESS_PREFIX}{title_suffix}"
            if t_idx > 0 and title_suffix == _STRESS_TASKS[0][1]:
                task_title = f"{STRESS_PREFIX}{title_suffix}-{t_idx + 1}"

            task = TmTask(
                project_id=proj.id,
                domain_id=domain.id,
                title=task_title[:200],
                requirement="钉钉日/周报超长压测：多 Task、多 Action、长说明、多风险",
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
                    summary="压测灌数：长文案日/周报",
                    detail="seed_daily_stress_long",
                )
            )

            created = 0
            with_risk = 0
            for i in range(1, n_actions + 1):
                topic = _TOPICS[topic_cursor % len(_TOPICS)]
                topic_cursor += 1
                owner = owners[(total_actions) % len(owners)]
                title = f"{STRESS_PREFIX}T{t_idx + 1}-{i:02d}-{topic}"
                action = TmAction(
                    task_id=task.id,
                    project_id=proj.id,
                    domain_id=domain.id,
                    week_start=period.week_start,
                    week_key=period.week_key,
                    title=title[:200],
                    owner_id=owner.id,
                    test_content=f"压测用例集-{topic}"[:1000],
                    environment="qa-stress",
                    status=STATUS_PUBLISHED,
                    created_by=admin.id,
                    published_at=now_tm(),
                    due_at=period.week_end,
                )
                db.add(action)
                db.flush()

                note = _LONG_NOTE_TEMPLATE.format(
                    i=i, i2=i + 4, topic=topic
                )[:1000]
                risk = ""
                # 仅前若干条带阻塞，贴近日常（默认最多 BLOCKER_ACTION_MAX）
                if total_risks + with_risk < BLOCKER_ACTION_MAX:
                    risk = _LONG_RISK_TEMPLATE.format(i=i, topic=topic)[:1000]
                    with_risk += 1
                db.add(
                    TmDailyUpdate(
                        action_id=action.id,
                        user_id=owner.id,
                        report_date=report_day,
                        progress_percent=min(95, 8 + i * 4 + t_idx * 3),
                        risk_blocker=risk,
                        progress_note=note,
                    )
                )
                created += 1
                total_actions += 1

            total_risks += with_risk
            print(
                f"  OK task={task_title} domain={domain.name} "
                f"actions={created} with_risk={with_risk}"
            )

        db.commit()
        print(
            f"  DONE tasks={n_tasks} actions={total_actions} "
            f"with_risk={total_risks} report_date={report_day}"
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def wipe_daily_stress_long() -> None:
    """硬删除【压测】Task/Action（不可恢复）。一般优先用 soft_delete_daily_stress_long。"""
    db = SessionLocal()
    try:
        print("== wipe daily stress ==")
        proj = db.query(TmProject).filter(TmProject.name == PROJECT_NAME).first()
        if not proj:
            print(f"  skip: no project {PROJECT_NAME}")
            return
        _wipe_stress_only(db, proj.id)
        db.commit()
        print("  OK wiped")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def soft_delete_daily_stress_long() -> None:
    """
    软删除【压测】数据：Task/Action 置为 cancelled。

    看板与日/周报不再展示，行与日更仍保留，便于事后回看。
    """
    from app.test_manage.config import STATUS_CANCELLED, TASK_STATUS_CANCELLED

    db = SessionLocal()
    try:
        print("== soft-delete daily stress ==")
        proj = db.query(TmProject).filter(TmProject.name == PROJECT_NAME).first()
        if not proj:
            print(f"  skip: no project {PROJECT_NAME}")
            return
        admin = (
            db.query(User)
            .filter(User.role.in_([UserRole.Admin, UserRole.Manager]))
            .order_by(User.id.asc())
            .first()
        )
        tasks = (
            db.query(TmTask)
            .filter(
                TmTask.project_id == proj.id,
                TmTask.title.like(f"{STRESS_PREFIX}%"),
            )
            .all()
        )
        n_task = 0
        for t in tasks:
            if t.status == TASK_STATUS_CANCELLED:
                continue
            prev = t.status
            t.status = TASK_STATUS_CANCELLED
            n_task += 1
            if admin:
                db.add(
                    TmTaskUpdateLog(
                        task_id=t.id,
                        user_id=admin.id,
                        summary="压测数据软删除（cancelled）",
                        detail=f"status: {prev} -> cancelled; soft_delete_daily_stress_long",
                    )
                )
        tids = [t.id for t in tasks]
        actions = (
            db.query(TmAction).filter(TmAction.task_id.in_(tids)).all() if tids else []
        )
        extra = (
            db.query(TmAction)
            .filter(
                TmAction.project_id == proj.id,
                TmAction.title.like(f"{STRESS_PREFIX}%"),
            )
            .all()
        )
        seen = {a.id for a in actions}
        for a in extra:
            if a.id not in seen:
                actions.append(a)
        n_act = 0
        for a in actions:
            if a.status == STATUS_CANCELLED:
                continue
            a.status = STATUS_CANCELLED
            n_act += 1
        db.commit()
        print(f"  OK soft-deleted tasks={n_task} actions={n_act} (rows kept)")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    # 默认 3 Task × 2 Action、约 4 条阻塞；要清数据可改调 soft_delete / wipe
    seed_daily_stress_long(task_count=TASK_COUNT, action_count=ACTION_COUNT_PER_TASK)
    # soft_delete_daily_stress_long()
    # wipe_daily_stress_long()
