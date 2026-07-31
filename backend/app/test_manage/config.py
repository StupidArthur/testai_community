"""
测试任务管理（项目管理）模块常量。

层级：Project → Domain → Task → Action（周轮回）
周边界：每周三 18:00 → 下一周三 18:00
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

# 业务时区：固定 UTC+8（避免 Windows 缺 tzdata）
TM_TZ = timezone(timedelta(hours=8), name="UTC+8")

WEEK_BOUNDARY_WEEKDAY = 2  # 周三
WEEK_BOUNDARY_HOUR = 18
WEEK_BOUNDARY_MINUTE = 0

STATUS_DRAFT = "draft"
STATUS_PUBLISHED = "published"
STATUS_DONE = "done"
STATUS_CANCELLED = "cancelled"

# 标记 Action「完成」要求的最新日更进度下限（未达不可 published→done）
ACTION_DONE_MIN_PROGRESS = 100

ACTION_STATUSES = frozenset({
    STATUS_DRAFT,
    STATUS_PUBLISHED,
    STATUS_DONE,
    STATUS_CANCELLED,
})

TASK_STATUS_DRAFT = "draft"
TASK_STATUS_PUBLISHED = "published"
TASK_STATUS_DONE = "done"
TASK_STATUS_CANCELLED = "cancelled"

# 产品口径：Task 仅「进行中 / 已完成」；draft/cancelled 仅兼容历史数据只读
TASK_STATUSES = frozenset({
    TASK_STATUS_DRAFT,
    TASK_STATUS_PUBLISHED,
    TASK_STATUS_DONE,
    TASK_STATUS_CANCELLED,
})
TASK_STATUSES_USER = frozenset({
    TASK_STATUS_PUBLISHED,
    TASK_STATUS_DONE,
})
# 可在本周新建 / 复制 Action 的 Task 状态
TASK_STATUSES_ALLOW_ACTION = frozenset({TASK_STATUS_PUBLISHED})

PROJECT_STATUS_ACTIVE = "active"
PROJECT_STATUS_ARCHIVED = "archived"

# 一期测试管理员账号（bootstrap 保证存在）
DEFAULT_MANAGER_USERNAME = "manager"
DEFAULT_MANAGER_PASSWORD = "123456"

# Task 需求内容最大字符数（前端展示计数与后端校验一致）
TASK_REQUIREMENT_MAX_CHARS = 5000

# 一般文本字段上限（风险、进度说明、更正、测试内容、环境等；不含需求）
TEXT_FIELD_MAX_CHARS = 1000

# Action 测试内容上限（与 TEXT_FIELD_MAX_CHARS 对齐）
ACTION_TEST_CONTENT_MAX_CHARS = TEXT_FIELD_MAX_CHARS
# Action 环境上限（产品要求短于一般文本）
ACTION_ENVIRONMENT_MAX_CHARS = 300

# ---------- 日更纪律 ----------
# 进度说明必填（去空白后非空即可，不限制最少字数）
DAILY_NOTE_MIN_CHARS = 1
# 当天日更可改写截止：默认 ≥19:50 锁定；企微日报默认 20:00 发送
DAILY_EDIT_LOCK_HOUR = int(os.getenv("TM_DAILY_EDIT_LOCK_HOUR", "19"))
DAILY_EDIT_LOCK_MINUTE = int(os.getenv("TM_DAILY_EDIT_LOCK_MINUTE", "50"))
# 测试可设 TM_DAILY_EDIT_LOCK_DISABLED=1 关闭锁定（须在 import app 前设置）
DAILY_EDIT_LOCK_DISABLED = os.getenv("TM_DAILY_EDIT_LOCK_DISABLED", "").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)

# 需重建的表（顺序：先子后父；不含推送快照——快照为增量建表，不随 schema 重建清空业务数据）
TM_TABLE_NAMES = (
    "tm_daily_updates",
    "tm_action_corrections",
    "tm_actions",
    "tm_task_update_logs",
    "tm_task_testers",
    "tm_tasks",
    "tm_domains",
    "tm_projects",
)

# ---------- 企业微信群推送（日报 / 周报）----------
REPORT_KIND_DAILY = "daily"
REPORT_KIND_WEEKLY = "weekly"
PUSH_TRIGGER_SCHEDULE = "schedule"
PUSH_TRIGGER_MANUAL = "manual"

# 企微 markdown 官方 content 上限 4096 字节；单条发送，禁止拆条
WECOM_MSG_MAX_BYTES = 4096
# 单条风险标题 / 正文截断（便于列表塞进单条）
WECOM_RISK_TITLE_MAX_CHARS = 36
WECOM_RISK_TEXT_MAX_CHARS = 72
# 风险条目 / 日更 Action / 周 Task 行初始上限；超长时递减
WECOM_PUSH_RISK_ITEMS_SOFT_MAX = 10
WECOM_DAILY_ACTION_LINES_SOFT_MAX = 24
WECOM_WEEKLY_TASK_ROWS_SOFT_MAX = 16

# 大屏「历史」下拉：不含本周，最多展示近 N 个业务周
HISTORY_WEEK_OPTIONS_MAX = 10

# 定时默认：日报每日 20:00；周报周三 17:30（周窗口切日前）
# 实际调度读取 platform.config（支持 .env 覆盖）
WECOM_DAILY_PUSH_HOUR = 20
WECOM_DAILY_PUSH_MINUTE = 0
WECOM_WEEKLY_PUSH_WEEKDAY = WEEK_BOUNDARY_WEEKDAY  # 周三
WECOM_WEEKLY_PUSH_HOUR = 17
WECOM_WEEKLY_PUSH_MINUTE = 30

# 调度轮询间隔（秒）
WECOM_SCHEDULER_POLL_SECONDS = 60


def now_tm() -> datetime:
    return datetime.now(TM_TZ)


def today_tm():
    """业务「今天」日期（UTC+8）。"""
    return now_tm().date()


def is_daily_edit_locked(now: datetime | None = None) -> bool:
    """
    当天日更是否已过截止：默认 ≥19:50 锁定。
    截止前可多次覆盖「今天」的日更；锁定后不可再写/改今日日更。
    """
    if DAILY_EDIT_LOCK_DISABLED:
        return False
    n = now or now_tm()
    if n.tzinfo is None:
        n = n.replace(tzinfo=TM_TZ)
    else:
        n = n.astimezone(TM_TZ)
    return (n.hour, n.minute) >= (DAILY_EDIT_LOCK_HOUR, DAILY_EDIT_LOCK_MINUTE)
