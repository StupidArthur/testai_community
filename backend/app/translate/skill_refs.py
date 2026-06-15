"""
Translate 各 Phase 的 SkillRef 配置。

None 表示仍使用 config/prompts/*.md 磁盘文件。
设置 SkillRef 后，Job 启动时会 resolve 并固化 resolved_version_id。
"""

from __future__ import annotations

from app.skill_hub.skill_ref import SkillRef

# Phase 2 Case 归纳 Prompt 来源；None = steps-2-cases-skill.md
PHASE2_SKILL_REF: SkillRef | None = None
