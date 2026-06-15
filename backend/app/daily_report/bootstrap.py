"""
工作日报 Skill 初始化与表结构迁移。
"""
from __future__ import annotations

import logging

from sqlalchemy import inspect, text

from app.auth.models import User, UserRole
from app.ai_service.work_daily.constants import WORK_DAILY_SKILL_NAME
from app.platform.database import SessionLocal, engine
from app.skill_hub.bootstrap import ensure_default_categories
from app.skill_hub.models import Branch, Skill, SkillVersion
from app.skill_hub.service import get_primary_admin_user, get_skill_by_name
from app.skill_hub.utils import dimensions_to_payload

log = logging.getLogger("app.daily_report")

_SKILL_9D = {
    "role": "测试工程师日报解析专家",
    "profile": (
        "- Author: TestAI Community\n"
        "- Version: 2.0\n"
        "- Language: 中文\n"
        "- Description: 审核测试团队日报的工作维度覆盖与工时占比完整性。"
    ),
    "background": (
        "用于统计测试工程师每日工作种类与工作量占比，支撑 AI 赋能全流程图。"
        "日报角色分为「测试工程师」「测试负责人」，与平台账号角色无关。"
    ),
    "goals": (
        "1. 识别日报中的工作种类（维度）及每项工时\n"
        "2. 计算或推断各项工作的工作量占比\n"
        "3. 审核是否写清「做了什么」和「投入多少时间」（两项硬性要求）\n"
        "4. 对缺失维度或占比信息给出可执行补充建议"
    ),
    "constraints": (
        "1. 仅输出 JSON，可包在 ```json 代码块内。\n"
        "2. 若缺少「工作内容」或「投入时间」，valid=false 并在 validation_issues、suggestions 用中文短句说明。\n"
        "3. suggestions 与 validation_issues 必须是字符串数组，禁止输出 dict 对象。\n"
        "4. 工作流程/内容反馈为可选，不因此判 invalid。\n"
        "5. 严禁编造用户未提及的工作项或工时。"
    ),
    "core_skills": (
        "1. 工作维度：功能测试、自动化、接口测试、评审、联调、文档、管理协调等。\n"
        "2. 工时解析：3h、半天、0.5d 等统一为小时（1d=8h）。\n"
        "3. 占比：各 work_items.ratio 之和应接近 1.0（允许±0.05 误差）。"
    ),
    "workflows": (
        "1. 阅读日期、日报角色与纯文本\n"
        "2. 抽取 work_items（category/description/hours/ratio）\n"
        "3. 检查 dimension_coverage 与 missing_dimensions\n"
        "4. 生成 suggestions 供用户补充\n"
        "5. 输出 JSON"
    ),
    "output_format": (
        "```json\n"
        "{\n"
        '  "valid": true,\n'
        '  "validation_issues": [],\n'
        '  "suggestions": [],\n'
        '  "work_items": [\n'
        '    {"category": "功能测试", "description": "...", "hours": 4, "ratio": 0.5}\n'
        "  ],\n"
        '  "total_hours": 8,\n'
        '  "dimension_coverage": ["功能测试", "自动化"],\n'
        '  "missing_dimensions": [],\n'
        '  "feedback": "可选流程反馈",\n'
        '  "summary": "一句话总结"\n'
        "}\n"
        "```"
    ),
    "initialization": "我是测试工程师日报解析专家，请提交待审核日报文本。",
}


def migrate_schema(_engine=None) -> None:
    """旧表含 unique / status 等字段时，重建为 v2 结构。"""
    eng = _engine or engine
    insp = inspect(eng)
    if not insp.has_table("daily_reports"):
        return
    cols = {c["name"] for c in insp.get_columns("daily_reports")}
    if "report_role" in cols and "audit_json" in cols:
        return

    log.info("daily_reports 表结构升级中…")
    with eng.begin() as conn:
        conn.execute(text("""
            CREATE TABLE daily_reports_new (
                id VARCHAR NOT NULL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                report_date DATE NOT NULL,
                report_role VARCHAR NOT NULL DEFAULT '测试工程师',
                raw_text TEXT NOT NULL,
                audit_json TEXT NOT NULL DEFAULT '{}',
                skill_version_id VARCHAR,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users (id),
                FOREIGN KEY(skill_version_id) REFERENCES skill_versions (id)
            )
        """))
        if "raw_text" in cols:
            conn.execute(text("""
                INSERT INTO daily_reports_new (id, user_id, report_date, report_role, raw_text, audit_json, skill_version_id, created_at)
                SELECT id, user_id, report_date, '测试工程师', raw_text,
                       COALESCE(structured_json, '{}'), skill_version_id, created_at
                FROM daily_reports
            """))
        conn.execute(text("DROP TABLE daily_reports"))
        conn.execute(text("ALTER TABLE daily_reports_new RENAME TO daily_reports"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_daily_reports_user_id ON daily_reports (user_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_daily_reports_report_date ON daily_reports (report_date)"))


def ensure_work_daily_skill(_engine=None) -> None:
    ensure_default_categories(_engine)
    db = SessionLocal()
    try:
        if get_skill_by_name(db, WORK_DAILY_SKILL_NAME):
            return
        admin = get_primary_admin_user(db) or db.query(User).filter(User.role == UserRole.Admin).first()
        if not admin:
            log.warning("work_daily: 无 Admin，跳过 Skill 创建")
            return

        skill = Skill(
            name=WORK_DAILY_SKILL_NAME,
            display_name="测试工程师日报解析",
            definition="审核日报工作维度与工时占比完整性，对应测试工程师日报解析。",
            category="documentation",
            tags='["工作日报", "审核"]',
        )
        db.add(skill)
        db.flush()
        master = Branch(skill_id=skill.id, user_id=admin.id, branch_type="master")
        standard = Branch(skill_id=skill.id, user_id=admin.id, branch_type="standard")
        db.add(master)
        db.add(standard)
        db.flush()
        payload = dimensions_to_payload(**_SKILL_9D)
        for i, bid in enumerate((standard.id, master.id)):
            db.add(SkillVersion(
                skill_id=skill.id, branch_id=bid, version_num=0, revision=i,
                commit_message="initial work daily parse v0",
                payload=payload,
                ai_commit_summary="工作日报解析 Skill 初始版本。",
            ))
        db.commit()
        log.info("work_daily: 已创建 Skill %s", WORK_DAILY_SKILL_NAME)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def ensure_daily_report_startup(_engine=None) -> None:
    migrate_schema(_engine)
    ensure_work_daily_skill(_engine)
