# Skill 调试功能变更说明

> 版本：2026-06-15

## 功能

进入 Skill 详情（分支列表页）后，点击 **「Skill 调试」** 进入沙箱：

- **左侧**：当前选中版本的 Skill Prompt（System Prompt，只读）
- **右侧**：用户输入 +「运行 Skill」+ 模型输出
- 可切换 **分支 / 版本**（默认 Master HEAD，无版本时回退 Standard）

所有登录用户可用；**不写库**，仅同步调用 LLM。

## 新增接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/skills/{skill_id}/debug/run` | 调试执行 |

请求体：

```json
{
  "user_input": "发送给 Skill 的内容",
  "version_id": "可选，pinned 指定版本",
  "branch_id": "可选，无 version_id 时用分支 HEAD"
}
```

## 变更文件

- `backend/app/skill_hub/service.py` — `run_skill_debug`
- `backend/app/skill_hub/schemas.py` — 请求/响应模型
- `backend/app/skill_hub/skills_router.py` — 路由
- `frontend/src/skill_hub/pages/SkillDebugPage.tsx` — 调试页
- `frontend/src/skill_hub/pages/SkillBranches.tsx` — 入口按钮
- `frontend/src/router.tsx` — `/skill/:skillId/debug`
- `frontend/src/shared/api/client.ts` — `skillsApi.debugRun`

## 注意

- 需配置 `MINIMAX_API_KEY`
- LLM 调用约 5–30 秒，前端超时 120s
- master 无版本时自动回退 standard（与 external API 一致）
