"""
需求进展：阶段常量校验、时间字段约束、与测试状态联动。

与 task.status（测试状态）分离：
- req_stage = 整需求生命周期
- status = 测试侧进行中 / 已完成 / 归档
"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import HTTPException

from app.test_manage.config import (
    REQ_STAGE_DEVELOPING,
    REQ_STAGE_LABELS,
    REQ_STAGE_PENDING_DEV,
    REQ_STAGE_PENDING_HANDOVER,
    REQ_STAGE_PENDING_TEST,
    REQ_STAGE_TEST_DONE,
    REQ_STAGE_TESTING,
    REQ_STAGES,
    REQ_STAGES_ALLOW_ACTION,
    TASK_STATUS_DONE,
    TASK_STATUS_PUBLISHED,
)


def req_stage_label(stage: str | None) -> str:
    """阶段码 → 中文标签。"""
    if not stage:
        return REQ_STAGE_LABELS[REQ_STAGE_PENDING_DEV]
    return REQ_STAGE_LABELS.get(stage, stage)


def normalize_req_stage(stage: str | None) -> str:
    """空值回退待开发。"""
    raw = (stage or "").strip()
    if not raw:
        return REQ_STAGE_PENDING_DEV
    if raw not in REQ_STAGES:
        raise HTTPException(status_code=400, detail=f"无效需求进展: {raw}")
    return raw


def can_add_action_for_req_stage(stage: str | None) -> bool:
    """仅「测试中」允许建 Action。"""
    return normalize_req_stage(stage) in REQ_STAGES_ALLOW_ACTION


def validate_req_stage_payload(
    *,
    stage: str,
    expected_handover_at: date | datetime | None,
    actual_handover_at: date | datetime | None,
    test_started_at: date | datetime | None,
    expected_test_end_at: date | datetime | None,
    test_ended_at: date | datetime | None,
) -> None:
    """
    校验需求进展码合法；各阶段关联时间**可留空（待定）**，不再硬必填。

    保留参数以便调用方统一传入、后续若要做「建议填写」提示可复用。
    """
    _ = (
        expected_handover_at,
        actual_handover_at,
        test_started_at,
        expected_test_end_at,
        test_ended_at,
    )
    normalize_req_stage(stage)


def sync_test_status_for_stage(stage: str) -> str | None:
    """
    进入特定需求进展时建议同步的测试状态。
    返回 None 表示不强制改 status。
    """
    stage = normalize_req_stage(stage)
    if stage == REQ_STAGE_TESTING:
        return TASK_STATUS_PUBLISHED
    if stage == REQ_STAGE_TEST_DONE:
        return TASK_STATUS_DONE
    if stage in (
        REQ_STAGE_PENDING_DEV,
        REQ_STAGE_DEVELOPING,
        REQ_STAGE_PENDING_HANDOVER,
        REQ_STAGE_PENDING_TEST,
    ):
        # 非测试投入阶段：保持 published 以便看板可见，但不允许 Action
        return TASK_STATUS_PUBLISHED
    return None


def stage_node_date_summary(
    *,
    stage: str | None,
    expected_handover_at: date | None,
    actual_handover_at: date | None,
    test_started_at: date | None,
    expected_test_end_at: date | None,
    test_ended_at: date | None,
) -> str:
    """大屏/卡片一行节点时间文案（缺日期写「待定」，不用「—」）。"""
    s = normalize_req_stage(stage)

    def fmt(d: date | None) -> str:
        return d.strftime("%m-%d") if d else "待定"

    if s == REQ_STAGE_PENDING_HANDOVER:
        return f"预计提测 {fmt(expected_handover_at)}" if expected_handover_at else "预计提测待定"
    if s == REQ_STAGE_PENDING_TEST:
        return f"已提测 {fmt(actual_handover_at)}" if actual_handover_at else "实际提测待定"
    if s == REQ_STAGE_TESTING:
        if not test_started_at:
            return "测试开始待定" if not expected_test_end_at else f"测试开始待定 ~ 预计结束 {fmt(expected_test_end_at)}"
        start = f"测试开始 {fmt(test_started_at)}"
        if expected_test_end_at:
            return f"{start} ~ 预计结束 {fmt(expected_test_end_at)}"
        return f"{start} ~ 预计结束待定"
    if s == REQ_STAGE_TEST_DONE:
        return f"测试结束 {fmt(test_ended_at)}" if test_ended_at else "测试结束待定"
    return ""
