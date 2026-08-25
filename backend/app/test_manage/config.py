"""
测试任务管理（项目管理）模块常量。

层级：Project → Domain → Task → Action（周轮回）
周边界：每周三 17:00 → 下一周三 17:00
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

# 业务时区：固定 UTC+8（避免 Windows 缺 tzdata）
TM_TZ = timezone(timedelta(hours=8), name="UTC+8")

WEEK_BOUNDARY_WEEKDAY = 2  # 周三
WEEK_BOUNDARY_HOUR = 17
WEEK_BOUNDARY_MINUTE = 0

# 周截止前编辑锁：周结束（默认周三 17:00）前 N 分钟起锁定 Action / Task 内容更新
WEEK_EDIT_LOCK_BEFORE_END_MINUTES = 5

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

# ---------- 需求进展（整需求生命周期，与测试状态 task.status 分离）----------
# 待开发 → 开发中 → 待提测 → 待测试 → 测试中 → 测试完成
REQ_STAGE_PENDING_DEV = "pending_dev"
REQ_STAGE_DEVELOPING = "developing"
REQ_STAGE_PENDING_HANDOVER = "pending_handover"  # 待提测
REQ_STAGE_PENDING_TEST = "pending_test"  # 待测试（已提测、等人）
REQ_STAGE_TESTING = "testing"  # 测试中
REQ_STAGE_TEST_DONE = "test_done"

REQ_STAGE_LABELS: dict[str, str] = {
    REQ_STAGE_PENDING_DEV: "待开发",
    REQ_STAGE_DEVELOPING: "开发中",
    REQ_STAGE_PENDING_HANDOVER: "待提测",
    REQ_STAGE_PENDING_TEST: "待测试",
    REQ_STAGE_TESTING: "测试中",
    REQ_STAGE_TEST_DONE: "测试完成",
}

REQ_STAGES = frozenset(REQ_STAGE_LABELS.keys())

# 仅测试中可新建 / 复制本周 Action
REQ_STAGES_ALLOW_ACTION = frozenset({REQ_STAGE_TESTING})

# 展示「测试状态」的阶段
REQ_STAGES_SHOW_TEST_STATUS = frozenset({REQ_STAGE_TESTING, REQ_STAGE_TEST_DONE})

# 大屏「需关注」默认盯的交测后阶段
REQ_STAGES_SCREEN_FOCUS = frozenset({REQ_STAGE_PENDING_TEST, REQ_STAGE_TESTING})

# 新建 Task 默认需求进展
REQ_STAGE_DEFAULT = REQ_STAGE_PENDING_DEV

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

# ---------- 钉钉群推送（日报 / 周报）----------
REPORT_KIND_DAILY = "daily"
REPORT_KIND_WEEKLY = "weekly"
PUSH_TRIGGER_SCHEDULE = "schedule"
PUSH_TRIGGER_MANUAL = "manual"

# 钉钉/群机器人单条上限口径（字节）；单条发送，禁止拆条
PUSH_MSG_MAX_BYTES = 4096
# 兼容旧常量名（测试与脚本若仍引用）
WECOM_MSG_MAX_BYTES = PUSH_MSG_MAX_BYTES
# 超长时 LLM 压缩目标（略小于硬上限，避免边界失败）
PUSH_AI_COMPRESS_TARGET_BYTES = int(os.getenv("DINGTALK_PUSH_AI_TARGET_BYTES", "3800"))
PUSH_AI_COMPRESS_ENABLED = os.getenv("DINGTALK_PUSH_AI_COMPRESS", "true").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
# AI 压缩总超时（秒）；字段总结 + 整篇压缩可能较慢，默认 90
PUSH_AI_COMPRESS_TIMEOUT_SEC = float(os.getenv("DINGTALK_PUSH_AI_TIMEOUT_SEC", "90"))
# 单条风险标题 / 正文截断（便于列表塞进单条）
PUSH_RISK_TITLE_MAX_CHARS = 36
PUSH_RISK_TEXT_MAX_CHARS = 72
WECOM_RISK_TITLE_MAX_CHARS = PUSH_RISK_TITLE_MAX_CHARS
WECOM_RISK_TEXT_MAX_CHARS = PUSH_RISK_TEXT_MAX_CHARS
# 风险条目 / 日更 Action / 周 Task 行初始上限；超长时递减
PUSH_RISK_ITEMS_SOFT_MAX = 10
PUSH_DAILY_ACTION_LINES_SOFT_MAX = 24
PUSH_WEEKLY_TASK_ROWS_SOFT_MAX = 16
WECOM_PUSH_RISK_ITEMS_SOFT_MAX = PUSH_RISK_ITEMS_SOFT_MAX
WECOM_DAILY_ACTION_LINES_SOFT_MAX = PUSH_DAILY_ACTION_LINES_SOFT_MAX
WECOM_WEEKLY_TASK_ROWS_SOFT_MAX = PUSH_WEEKLY_TASK_ROWS_SOFT_MAX

# 大屏「历史」下拉：不含本周，最多展示近 N 个业务周
HISTORY_WEEK_OPTIONS_MAX = 10

# 日/周报页脚「详情」链接（完整可点 URL）
DEFAULT_BOARD_DETAIL_URL = "http://10.30.144.64:48011/projects"
DINGTALK_BOARD_URL = (os.getenv("DINGTALK_BOARD_URL") or DEFAULT_BOARD_DETAIL_URL).strip()
PUBLIC_APP_ORIGIN = (os.getenv("PUBLIC_APP_ORIGIN") or "").strip().rstrip("/")
# 公开只读大屏路径（免登录）
PUBLIC_SCREEN_PATH = "/tm-screen"
# 日报截图：Playwright 打开公开今日大屏
DINGTALK_DAILY_SCREENSHOT_ENABLED = os.getenv(
    "DINGTALK_DAILY_SCREENSHOT_ENABLED", "true"
).strip().lower() in ("1", "true", "yes", "on")
DINGTALK_SCREENSHOT_TIMEOUT_MS = int(os.getenv("DINGTALK_SCREENSHOT_TIMEOUT_MS", "45000"))
DINGTALK_SCREENSHOT_VIEWPORT_WIDTH = int(
    os.getenv("DINGTALK_SCREENSHOT_VIEWPORT_WIDTH", "1440")
)
DINGTALK_SCREENSHOT_VIEWPORT_HEIGHT = int(
    os.getenv("DINGTALK_SCREENSHOT_VIEWPORT_HEIGHT", "2200")
)


def _origin_from_url(url: str) -> str:
    """从完整 URL 取 scheme://host[:port]。"""
    raw = (url or "").strip()
    if not raw:
        return ""
    try:
        from urllib.parse import urlparse

        p = urlparse(raw)
        if p.scheme and p.netloc:
            return f"{p.scheme}://{p.netloc}".rstrip("/")
    except Exception:  # noqa: BLE001
        return ""
    return ""


def resolve_public_app_origin() -> str:
    """公开前端根地址：PUBLIC_APP_ORIGIN > DINGTALK_BOARD_URL 的 origin > 默认生产。"""
    if PUBLIC_APP_ORIGIN:
        return PUBLIC_APP_ORIGIN
    from_board = _origin_from_url(DINGTALK_BOARD_URL)
    if from_board:
        return from_board
    return _origin_from_url(DEFAULT_BOARD_DETAIL_URL) or "http://10.30.144.64:48011"


def resolve_public_today_screen_url(
    *,
    project_id: str | None = None,
    screenshot: bool = False,
) -> str:
    """
    今日公开大屏深链（免鉴权只读）。
    screenshot=True 时带截图友好参数，供 Playwright 使用。
    """
    return resolve_public_screen_url(
        view="today", project_id=project_id, screenshot=screenshot
    )


def resolve_public_week_screen_url(
    *,
    project_id: str | None = None,
    screenshot: bool = False,
) -> str:
    """本周公开大屏深链（view=current）。"""
    return resolve_public_screen_url(
        view="current", project_id=project_id, screenshot=screenshot
    )


def resolve_public_screen_url(
    *,
    view: str = "today",
    project_id: str | None = None,
    screenshot: bool = False,
) -> str:
    """
    公开大屏深链（免鉴权只读）。
    view: today | current | history
    screenshot=True 时带截图友好参数，供 Playwright 使用。
    """
    from urllib.parse import urlencode

    origin = resolve_public_app_origin()
    mode = (view or "today").strip().lower() or "today"
    q: dict[str, str] = {"view": mode}
    if project_id:
        q["project_id"] = project_id
    if screenshot:
        q["screenshot"] = "1"
    return f"{origin}{PUBLIC_SCREEN_PATH}?{urlencode(q)}"


def resolve_board_detail_url() -> str:
    """
    钉钉消息「详情」链接：默认公开今日大屏深链（免鉴权）。
    可用 DINGTALK_DETAIL_URL 完全覆盖；若 DINGTALK_BOARD_URL 已含 /tm-screen 也直接用。
    """
    detail_override = (os.getenv("DINGTALK_DETAIL_URL") or "").strip()
    if detail_override:
        return detail_override
    if PUBLIC_SCREEN_PATH in (DINGTALK_BOARD_URL or ""):
        return DINGTALK_BOARD_URL
    return resolve_public_today_screen_url()


def resolve_week_board_detail_url() -> str:
    """周报详情链：公开本周大屏（可用 DINGTALK_WEEKLY_DETAIL_URL 覆盖）。"""
    override = (os.getenv("DINGTALK_WEEKLY_DETAIL_URL") or "").strip()
    if override:
        return override
    return resolve_public_week_screen_url()

# 定时默认：日报每日 20:00；周报发送由 week_end+15min 推导（下列仅兜底文档）
DINGTALK_DAILY_PUSH_HOUR = 20
DINGTALK_DAILY_PUSH_MINUTE = 0
DINGTALK_WEEKLY_PUSH_WEEKDAY = WEEK_BOUNDARY_WEEKDAY  # 周三
DINGTALK_WEEKLY_PUSH_HOUR = 17
DINGTALK_WEEKLY_PUSH_MINUTE = 30
WECOM_DAILY_PUSH_HOUR = DINGTALK_DAILY_PUSH_HOUR
WECOM_DAILY_PUSH_MINUTE = DINGTALK_DAILY_PUSH_MINUTE
WECOM_WEEKLY_PUSH_WEEKDAY = DINGTALK_WEEKLY_PUSH_WEEKDAY
WECOM_WEEKLY_PUSH_HOUR = DINGTALK_WEEKLY_PUSH_HOUR
WECOM_WEEKLY_PUSH_MINUTE = DINGTALK_WEEKLY_PUSH_MINUTE

# 调度轮询间隔（秒）
PUSH_SCHEDULER_POLL_SECONDS = 60
WECOM_SCHEDULER_POLL_SECONDS = PUSH_SCHEDULER_POLL_SECONDS


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
