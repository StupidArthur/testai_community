"""
QA-SkillHub Seed Script

执行：cd qa-skillhub/backend && python scripts/seed_db.py

行为：
  1. drop_all + create_all 彻底重置库结构
  2. 3 个用户：admin (Admin) / alice (Engineer) / arthur (Engineer)
     密码 = 用户名
  3. 1 个标准 Skill：API_Test_Generator
  4. 4 个 Branch：
     - admin 持有 master（主干）+ standard（标准模板）2 条系统级分支
     - alice 持有 personal
     - arthur 持有 personal
  5. 每个 Branch 写入 1 个 v0 初始版本
"""
from __future__ import annotations

import sys
from pathlib import Path

# Windows 控制台 GBK 兼容
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.auth.models import User, UserRole  # noqa: E402
from app.auth.service import hash_password  # noqa: E402
from app.skill_hub.models import Skill, Branch, SkillVersion  # noqa: E402

# ============================================================
# 9 维模板数据：standard（标准模板）—— 全员 fork 起点
# ============================================================
STANDARD_9D = {
    "role": "资深 API 自动化测试专家",
    "profile": (
        "- Author: QA Architect Team\n"
        "- Version: 2.0\n"
        "- Language: 中文\n"
        "- Description: 专注于精准解析 API 文档，并自动生成覆盖边界值与异常流的高可用测试用例。"
    ),
    "background": (
        "QA 团队在日常迭代中需要面对大量 RESTful/GraphQL 接口；"
        "传统手工编写测试用例耗时且易遗漏边界与异常路径。"
        "本 Skill 以 LangGPT 9 维规范为骨架，确保生成的测试用例覆盖度与规范性。"
    ),
    "goals": (
        "1. 解析 API 文档（JSON / Swagger / YApi）\n"
        "2. 提取关键字段的数据类型与约束\n"
        "3. 推演正常路径 + 异常边界 + 基础安全测试用例\n"
        "4. 输出标准 Markdown 表格供 QA 直接落地"
    ),
    "constraints": (
        "1. 必须严格遵循「等价类划分」和「边界值分析」原则。\n"
        "2. 必须包含正向测试（Happy Path）、逆向测试以及基础的安全测试（如 SQL 注入、越权尝试）。\n"
        "3. 输出结果必须严格使用 Markdown 标准表格。\n"
        "4. 严禁省略前置条件列；严禁把多条用例压缩到一行。"
    ),
    "core_skills": (
        "1. 解析 OpenAPI 3.0 / Swagger / YApi 三种格式，自动识别 Method/URL/Headers/Params。\n"
        "2. 对每个必填字段做等价类划分（有效 / 无效 / 边界）。\n"
        "3. 自动生成 SQL 注入 / XSS 越权等基础安全用例模板。\n"
        "4. 严格按 Markdown 表格输出（用例编号 / 测试模块 / 前置条件 / 输入参数 / 预期结果）。"
    ),
    "workflows": (
        "1. 第一步：解析用户提供的 API 文档，提取 Method/URL/Headers/Params。\n"
        "2. 第二步：识别每个关键字段的数据类型、约束条件（必填、长度、范围、正则）。\n"
        "3. 第三步：推演正常路径测试用例。\n"
        "4. 第四步：推演异常与安全边界测试用例。\n"
        "5. 第五步：将所有用例汇总输出为 Markdown 标准表格。"
    ),
    "output_format": (
        "```markdown\n"
        "| 用例编号 | 测试模块 | 前置条件 | 输入参数 | 预期结果 |\n"
        "|---------|---------|---------|---------|---------|\n"
        "| TC001   | 用户登录 | 账号存在 | username=alice&password=xxx | 200 + 返回 token |\n"
        "| TC002   | 用户登录 | 账号不存在 | username=ghost | 404 |\n"
        "```\n"
    ),
    "initialization": (
        "作为资深 API 自动化测试专家，我已经准备好为您生成高覆盖率的测试用例。"
        "请提供您的接口文档片段（支持 JSON、Swagger 或 YApi 格式）。"
    ),
}

# master 主干预置：跟 standard 一样的 9 维作为发布起点
MASTER_9D = {
    "role": "API 自动化测试 Skill 主干",
    "profile": (
        "- Author: System Master\n"
        "- Version: 1.0\n"
        "- Language: 中文\n"
        "- Description: 由 standard 合并而来，作为正式发布版本。"
    ),
    "background": "正式发布版本；由 admin 从 standard v0 合并而来。",
    "goals": "为 QA 团队提供生产可用的 API 测试用例生成能力。",
    "constraints": "保持 9 维结构完整性；任何修改必须经过 PR 评审。",
    "core_skills": "继承自 standard 的全部核心能力。",
    "workflows": "继承自 standard 的全部工作流。",
    "output_format": "继承自 standard 的输出格式。",
    "initialization": "我是 API 自动化测试主干预置版本。",
}


def _add_user(db, username: str, role: UserRole) -> User:
    u = User(username=username, password_hash=hash_password(username), role=role)
    db.add(u)
    db.flush()
    return u


def _add_branch(db, skill_id: str, user_id: int, branch_type: str) -> Branch:
    b = Branch(skill_id=skill_id, user_id=user_id, branch_type=branch_type)
    db.add(b)
    db.flush()
    return b


def _add_version(db, skill_id: str, branch_id: int, version_num: int, payload: dict,
                 commit_message: str, ai_summary: str) -> SkillVersion:
    v = SkillVersion(
        skill_id=skill_id,
        branch_id=branch_id,
        version_num=version_num,
        commit_message=commit_message,
        ai_commit_summary=ai_summary,
        **payload,
    )
    db.add(v)
    db.flush()
    return v


def main() -> None:
    print(">> drop_all + create_all (彻底重置库结构)...")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        print(">> 写入 3 个用户 (密码 = 用户名)...")
        admin = _add_user(db, "admin", UserRole.Admin)
        alice = _add_user(db, "alice", UserRole.Engineer)
        arthur = _add_user(db, "arthur", UserRole.Engineer)
        print(f"   admin(id={admin.id}, Admin)")
        print(f"   alice(id={alice.id}, Engineer)")
        print(f"   arthur(id={arthur.id}, Engineer)")

        print(">> 写入 Skill: API_Test_Generator...")
        skill = Skill(
            name="API_Test_Generator",
            display_name="API 测试用例生成专家",
            definition="为 QA 团队生成高覆盖率的 API 测试用例，支持 Swagger/YApi/JSON 文档。",
        )
        db.add(skill)
        db.flush()
        print(f"   skill.id = {skill.id}")

        print(">> 写入 4 个 Branch...")
        master_branch = _add_branch(db, skill.id, admin.id, "master")
        template_branch = _add_branch(db, skill.id, admin.id, "template")
        alice_personal = _add_branch(db, skill.id, alice.id, "personal")
        arthur_personal = _add_branch(db, skill.id, arthur.id, "personal")
        print(f"   admin  → master(#{master_branch.id}) + template(#{template_branch.id})")
        print(f"   alice  → personal(#{alice_personal.id})")
        print(f"   arthur → personal(#{arthur_personal.id})")

        print(">> 写入 4 个 v0 版本...")
        _add_version(
            db, skill.id, template_branch.id, 0, STANDARD_9D,
            commit_message="initial 9-dimension standard template",
            ai_summary="🟢 初始版本：建立了 9 维结构骨架，6 个核心 Agent 设定维度全部填充。",
        )
        _add_version(
            db, skill.id, master_branch.id, 0, MASTER_9D,
            commit_message="initial master seed",
            ai_summary="🟢 初始主干：与 standard v0 对齐作为发布起点。",
        )
        _add_version(
            db, skill.id, alice_personal.id, 0, STANDARD_9D,
            commit_message="alice's fork of standard v0",
            ai_summary="🔵 Fork 自 standard v0，alice 的个人分支。",
        )
        _add_version(
            db, skill.id, arthur_personal.id, 0, STANDARD_9D,
            commit_message="arthur's fork of standard v0",
            ai_summary="🔵 Fork 自 standard v0，arthur 的个人分支。",
        )
        db.commit()

        print(
            f"\n[OK] seed 完成。\n"
            f"     账号（密码=用户名）：admin / alice / arthur\n"
            f"     Skill: API_Test_Generator (id={skill.id})\n"
            f"     4 Branch: master / template / alice personal / arthur personal"
        )
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        print(f"[FAIL] seed 失败，已回滚：{exc!r}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
