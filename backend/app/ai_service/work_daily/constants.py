"""工作日报模块常量。"""

from __future__ import annotations

# Skill 名称（skill_hub master HEAD），对应「测试工程师日报解析」
WORK_DAILY_SKILL_NAME = "Test_Engineer_Daily_Report_Parse"

REPORT_ROLES: tuple[str, ...] = ("测试工程师", "测试负责人")

MAX_DAYS_BACK = 7
MAX_RAW_TEXT_LENGTH = 8000
