"""工作流编排：Phase 1 → Phase 2 → Phase 4"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .audit import LlmAudit
from .config import PHASE1_BATCH_SIZE, PHASE2_WINDOW_SIZE, PHASE4_WINDOW_SIZE
from .models import EnrichedAction, StructuredStep
from .phases.phase1 import run_phase1
from .phases.phase2 import Phase2Result, run_phase2
from .phases.phase4 import run_phase4
from .xml_parse import max_sliding_window_rounds

log = logging.getLogger(__name__)


@dataclass
class WorkflowResult:
    steps_file: Path | None = None
    cases_file: Path | None = None
    agent_txt_file: Path | None = None
    fallback_applied: bool = False
    fallback_indices: list[int] = field(default_factory=list)
    cases_fallback_file: str | None = None


ProgressCallback = Callable[[str, int, int, str], None]


async def run_workflow(
    run_dir: Path,
    enriched_actions: list[EnrichedAction],
    *,
    phase1_batch_size: int = PHASE1_BATCH_SIZE,
    phase2_window_size: int = PHASE2_WINDOW_SIZE,
    phase4_window_size: int = PHASE4_WINDOW_SIZE,
    client=None,
    log_instance=None,
    progress_callback: ProgressCallback | None = None,
) -> WorkflowResult:
    _log = log_instance or log

    audit = LlmAudit(run_dir, _log)

    progress_state = {"offset": 0, "total": 0}

    def _safe_emit(phase: str, step: int, total: int, message: str) -> None:
        if progress_callback is None:
            return
        try:
            progress_callback(phase, step, total, message)
        except Exception:
            _log.exception("[Workflow] progress_callback raised")

    def _wrapped(phase: str, in_step: int, _in_total: int, message: str) -> None:
        _safe_emit(phase, progress_state["offset"] + in_step, progress_state["total"], message)

    p1_estimate = max(1, math.ceil(len(enriched_actions) / max(phase1_batch_size, 1)))
    estimate_total = 1 + p1_estimate + 1 + 1 + 1

    _log.info(f"[Phase 1] 正在生成结构化步骤 (批次大小={phase1_batch_size})...")
    progress_state["offset"] = 1
    progress_state["total"] = estimate_total
    _wrapped("phase1", 0, 0, f"[Phase 1] 开始 (输入 {len(enriched_actions)} 条，预计 {p1_estimate} 批次)")
    phase1_dir = run_dir / "translate" / "phase1"
    phase1_dir.mkdir(parents=True, exist_ok=True)

    steps, errors, p1_calls = await run_phase1(
        run_dir, enriched_actions,
        batch_size=phase1_batch_size, audit=audit, log=_log,
        progress_callback=_wrapped,
    )

    _log.info(f"[Phase 1] 完成，共 {len(steps)} 条结构化步骤")
    if errors:
        _log.warning(f"[Phase 1] 存在 {len(errors)} 条 LLM 输出异常")

    effective = [s for s in steps if s.status in ("normal", "fallback")]
    p2_total = max(1, max_sliding_window_rounds(len(effective), phase2_window_size))
    p4_total = max(1, max_sliding_window_rounds(len(effective), PHASE4_WINDOW_SIZE))
    total_after_p1 = 1 + p1_calls + p2_total + p4_total + 1
    progress_state["total"] = total_after_p1
    _wrapped("phase1", p1_calls, 0, f"[Phase 1] 完成, 共 {len(steps)} 条 (实际 LLM 调用 {p1_calls} 次)")

    _log.info(f"[Phase 2] 正在归纳测试用例 (窗口大小={phase2_window_size})...")
    progress_state["offset"] = 1 + p1_calls
    _wrapped("phase2", 0, 0, f"[Phase 2] 开始 (预计 {p2_total} 轮)")
    cases_file = run_dir / "translate" / "phase2" / "cases.md"

    phase2_result, p2_calls = await run_phase2(
        run_dir, steps,
        window_size=phase2_window_size, audit=audit, log=_log,
        progress_callback=_wrapped,
    )

    _log.info(f"[Phase 2] 完成")
    if phase2_result.fallback_applied:
        _log.warning(f"[Phase 2] 兜底已介入，缺失 {len(phase2_result.fallback_indices)} 步")

    total_after_p2 = 1 + p1_calls + p2_calls + p4_total + 1
    progress_state["total"] = total_after_p2
    _wrapped("phase2", p2_calls, 0, f"[Phase 2] 完成 (实际 LLM 调用 {p2_calls} 次)")

    progress_state["offset"] = 1 + p1_calls + p2_calls
    _wrapped("phase4", 0, 0, f"[Phase 4] 开始 (预计 {p4_total} 批)")
    agent_txt_file = None
    try:
        agent_txt_file, p4_calls = await run_phase4(
            run_dir, steps,
            window_size=phase4_window_size, audit=audit, log=_log,
            progress_callback=_wrapped,
        )
    except Exception as e:
        _log.error(f"[Workflow] Agent TXT 生成失败: {e}")
        p4_calls = 0

    total_final = 1 + p1_calls + p2_calls + p4_calls + 1
    progress_state["total"] = total_final
    _wrapped("phase4", p4_calls, 0, f"[Phase 4] 完成 (实际 LLM 调用 {p4_calls} 次)")

    _wrapped("finalize", total_final - 1, 0, "打包审计与产物中...")
    audit.finalize()
    _safe_emit("finalize", total_final - 1, total_final, "完成")

    return WorkflowResult(
        steps_file=phase1_dir / "structured_steps.json",
        cases_file=cases_file,
        agent_txt_file=agent_txt_file,
        fallback_applied=phase2_result.fallback_applied,
        fallback_indices=phase2_result.fallback_indices,
        cases_fallback_file=phase2_result.fallback_file,
    )
