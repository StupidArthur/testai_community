"""
工作日报 Skill 审核：解析工作维度、工时占比与完整性。
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.ai_service.client import chat
from app.ai_service.work_daily.constants import WORK_DAILY_SKILL_NAME
from app.ai_service.work_daily.models import WorkDailyAuditResult, WorkItem
from app.skill_hub.models import Branch
from app.skill_hub.service import (
    get_branch_head_version,
    get_skill_by_name,
    resolve_skill_ref,
)
from app.skill_hub.skill_ref import ResolveMode, SkillRef

log = logging.getLogger("app.ai_service.work_daily")

# 审核 LLM 参数：缩短输出、减少重试以提升响应速度
AUDIT_MAX_TOKENS = 2048
AUDIT_MAX_RETRIES = 1


def _build_user_message(raw_text: str, report_date: date, report_role: str) -> str:
    return (
        f"【日报日期】{report_date.isoformat()}\n"
        f"【日报角色】{report_role}\n\n"
        f"【待审核纯文本】\n{raw_text.strip()}\n\n"
        "请按 Output Format 输出 JSON。suggestions 与 validation_issues 必须是字符串数组。"
    )


def _parse_json(raw: str) -> dict:
    text = (raw or "").strip()
    if not text:
        return {}
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            try:
                data = json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return {}
        else:
            return {}
    return data if isinstance(data, dict) else {}


def _format_list_item(item: object) -> str:
    """将 LLM 返回的字符串或结构化 dict 转为可读中文。"""
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        detail = str(item.get("detail") or item.get("message") or item.get("text") or "").strip()
        if detail:
            type_ = str(item.get("type") or "").strip()
            severity = str(item.get("severity") or "").strip()
            if type_ and severity:
                return f"[{type_}/{severity}] {detail}"
            if type_:
                return f"[{type_}] {detail}"
            return detail
        return json.dumps(item, ensure_ascii=False)
    return str(item).strip()


def _text_list(data: dict, key: str) -> list[str]:
    raw = data.get(key) or []
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        text = _format_list_item(item)
        if text:
            out.append(text)
    return out


def _normalize(data: dict) -> WorkDailyAuditResult:
    items_raw = data.get("work_items") or data.get("projects") or []
    work_items: list[WorkItem] = []
    if isinstance(items_raw, list):
        for item in items_raw:
            if not isinstance(item, dict):
                continue
            try:
                hours = float(item.get("hours") or 0)
            except (TypeError, ValueError):
                hours = 0.0
            try:
                ratio = float(item.get("ratio") or 0)
            except (TypeError, ValueError):
                ratio = 0.0
            work_items.append(
                WorkItem(
                    category=str(item.get("category") or item.get("name") or "").strip(),
                    description=str(item.get("description") or item.get("work_summary") or "").strip(),
                    hours=hours,
                    ratio=ratio,
                )
            )

    try:
        total_hours = float(data.get("total_hours") or 0)
    except (TypeError, ValueError):
        total_hours = sum(w.hours for w in work_items)

    suggestions = _text_list(data, "suggestions")
    if not suggestions:
        suggestions = _text_list(data, "validation_issues")

    return WorkDailyAuditResult(
        valid=bool(data.get("valid", True)),
        validation_issues=_text_list(data, "validation_issues"),
        suggestions=suggestions,
        work_items=work_items,
        total_hours=total_hours,
        dimension_coverage=_text_list(data, "dimension_coverage"),
        missing_dimensions=_text_list(data, "missing_dimensions"),
        feedback=str(data.get("feedback") or "").strip(),
        summary=str(data.get("summary") or "").strip(),
    )


def get_work_daily_standard_version_id(db: Session) -> str | None:
    """落库用 standard 分支 HEAD 版本 id。"""
    skill = get_skill_by_name(db, WORK_DAILY_SKILL_NAME)
    if not skill:
        return None
    standard = (
        db.query(Branch)
        .filter(Branch.skill_id == skill.id, Branch.branch_type == "standard")
        .first()
    )
    if not standard:
        return None
    head = get_branch_head_version(db, standard.id)
    return head.id if head else None


async def audit_work_daily(
    db: Session,
    raw_text: str,
    report_date: date,
    report_role: str,
) -> tuple[WorkDailyAuditResult, str | None]:
    """
    调用 skill_hub master 最新版 Skill 审核日报；落库版本 id 为 standard HEAD。

    Returns:
        (audit_result, standard_skill_version_id)
    """
    skill = get_skill_by_name(db, WORK_DAILY_SKILL_NAME)
    if not skill:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"工作日报 Skill 未就绪：{WORK_DAILY_SKILL_NAME}",
        )

    resolved = resolve_skill_ref(
        db,
        SkillRef(
            resolve_mode=ResolveMode.branch_head,
            skill_name=skill.name,
            branch_type="master",
        ),
    )

    messages = [
        {"role": "system", "content": resolved.payload},
        {"role": "user", "content": _build_user_message(raw_text, report_date, report_role)},
    ]

    try:
        raw = await chat(
            messages,
            temperature=0.1,
            max_tokens=AUDIT_MAX_TOKENS,
            think=False,
            max_retries=AUDIT_MAX_RETRIES,
        )
    except Exception as exc:
        log.warning("work daily audit failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI 审核服务暂时不可用，请稍后重试",
        ) from exc

    record_version_id = get_work_daily_standard_version_id(db)
    return _normalize(_parse_json(raw)), record_version_id
