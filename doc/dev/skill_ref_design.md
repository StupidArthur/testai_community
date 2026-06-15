# SkillRef 跨模块版本引用设计

## 概述

业务模块（translate、external_api 等）通过 **SkillRef** JSON 描述「要用哪个 Skill 的哪个版本」，由 `skill_hub.service.resolve_skill_ref()` 统一解析为不可变 **ResolvedSkill**。

## 三层版本标识

| 层级 | 字段 | 用途 |
|------|------|------|
| 分支版本 | `branch_id` + `version_num` | 沙箱时间线、Release #N（master） |
| 全局序号 | `revision` | Skill 内单调递增，审计排序 |
| 稳定引用 | `version_id` (UUID) | pin、Job 固化 |

**禁止**仅用 `skill_name + version_num` 跨分支定位。

## SkillRef 字段

### resolve_mode: `pinned`

锁定某一快照，必填 `version_id`：

```json
{
  "resolve_mode": "pinned",
  "version_id": "uuid-...",
  "skill_name": "API_Test_Generator"
}
```

### resolve_mode: `branch_head`

浮动到分支 HEAD，必填 `skill_name` + 分支定位：

```json
{
  "resolve_mode": "branch_head",
  "skill_name": "API_Test_Generator",
  "branch_type": "master"
}
```

分支定位优先级：`branch_id` > `branch_type` + `owner_user_id`（personal）> 默认 `master`。

## 前端选用流程

1. **引用模式**：跟随 HEAD / 锁定快照
2. **Skill**：列表或分类筛选
3. **Branch**：master / standard / personal
4. **版本**（仅锁定模式）：时间线点选 → 存 `version_id`

组件：`frontend/src/skill_hub/components/SkillRefPicker.tsx`

## HTTP API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/skills/resolve` | Body: SkillRef → ResolvedSkill |
| GET | `/api/v1/external/skills/{name}` | Query: `version_id` / `branch_id` / `branch_type` |

master 无版本时 external API 回退到 standard HEAD（兼容旧行为）。

## 业务 Job 固化

长任务启动时：

1. `resolved = resolve_skill_ref(db, ref)`
2. 写入 `skill_ref_json` + `resolved_version_id`

## 对外暴露符号（进程内 import）

- `SkillRef`, `ResolvedSkill`, `ResolveMode`
- `resolve_skill_ref`, `get_skill_version_by_id`
- `version_to_langgpt_payload`, `version_to_fields`
- `build_version_locator_for_version`

禁止业务模块直接 `db.query(SkillVersion)`。

## 运营约定

- **生产**：`pinned` 或 `branch_head + master`
- **调试**：可引用 personal；Job 须记录 `resolved_version_id`
