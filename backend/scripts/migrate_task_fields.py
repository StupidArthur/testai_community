"""
tm_tasks 新字段迁移脚本（配合 Task 属性扩展：SR编号/子类模块/需求类型/优先级/变更标识/验收标准/验证三件套/备注）
执行位置：任意位置（自动探测数据库路径）

操作：
  1. 自动查找数据库（同 reset_prod_for_launch.py 的探测逻辑）
  2. ALTER TABLE tm_tasks 增加新列（已存在则跳过）
  3. TPT v2.3 项目数据回填：
     - requirement 中的「子类：xxx」提取到 module 列，需求正文去掉该前缀
     - 按标题匹配 seed 数据回填 sr_code / priority
  4. 其他项目 Task：仅提取「子类：」前缀到 module（如有）
"""

import re
import sqlite3
import sys
from pathlib import Path

CANDIDATE_DIRS = [
    r"D:\testai_community_prod\backend",
    r"D:\deploy\testai_community_prod\backend",
    r"D:\testai_community_prod",
    r"D:\deploy\testai_community_prod",
]

DB_FILENAMES = ["database_prod.sqlite", "database.sqlite"]

NEW_COLUMNS = [
    ("sr_code", "TEXT NOT NULL DEFAULT ''"),
    ("ir_codes", "TEXT NOT NULL DEFAULT ''"),
    ("module", "TEXT NOT NULL DEFAULT ''"),
    ("req_type", "TEXT NOT NULL DEFAULT ''"),
    ("priority", "TEXT NOT NULL DEFAULT ''"),
    ("change_flag", "TEXT NOT NULL DEFAULT ''"),
    ("acceptance_criteria", "TEXT NOT NULL DEFAULT ''"),
    ("verifier_id", "INTEGER"),
    ("verified_at", "DATE"),
    ("verify_result", "TEXT NOT NULL DEFAULT ''"),
    ("remark", "TEXT NOT NULL DEFAULT ''"),
]

PROJECT_NAME = "TPT v2.3 产品包"

# (域, 标题) → (SR编号, 优先级)；来自 seed_tpt_v23_basic.py 的 SRS 数据
# 注意：同名「国产化改造」有两条（SR-22 计划调度域 / SR-29 智能仿真域），须按域区分
SRS_META: dict[tuple[str, str], tuple[str, str]] = {
    ("TPT平台", "智能问数功能增强"): ("SR-TPT-00001", "高"),
    ("TPT平台", "数据中心功能增强"): ("SR-TPT-00002", "高"),
    ("TPT平台", "微服务功能增强"): ("SR-TPT-00003", "高"),
    ("TPT平台", "计算引擎功能增强"): ("SR-TPT-00004", "高"),
    ("TPT平台", "算子优化功能增强"): ("SR-TPT-00005", "高"),
    ("TPT平台", "系统硬件适配功能增强"): ("SR-TPT-00006", "高"),
    ("TPT平台", "云原生技术功能增强"): ("SR-TPT-00007", "高"),
    ("TPT平台", "国际化适配"): ("SR-TPT-00008", "高"),
    ("TPT平台", "我的Agent功能增强"): ("SR-TPT-00009", "高"),
    ("TPT平台", "我的应用功能增强"): ("SR-TPT-00010", "高"),
    ("TPT平台", "我的对话功能增强"): ("SR-TPT-00011", "高"),
    ("TPT平台", "平台基本能力功能增强"): ("SR-TPT-00012", "高"),
    ("TPT平台", "SCOPE能力功能增强"): ("SR-TPT-00013", "高"),
    ("TPT平台", "LLM能力功能增强"): ("SR-TPT-00014", "高"),
    ("智能控制Agents", "智能控制融合"): ("SR-TPT-00015", "高"),
    ("智能控制Agents", "操作导航融合"): ("SR-TPT-00016", "高"),
    ("回路优化Agents", "回路优化融合"): ("SR-TPT-00017", "高"),
    ("报警管理Agents", "报警管理融合"): ("SR-TPT-00018", "高"),
    ("设备健康监测Agents/设备诊断Agents", "设备健康监测TPT融合"): ("SR-TPT-00019", "高"),
    ("utilities Agents", "软测量能力"): ("SR-TPT-00020", "高"),
    ("设备健康监测Agents/设备诊断Agents", "AI能力提升需求"): ("SR-TPT-00021", "高"),
    ("计划调度优化Agents", "国产化改造"): ("SR-TPT-00022", "高"),
    ("计划调度优化Agents", "自动测算、模型校核、结果分析融合"): ("SR-TPT-00023", "高"),
    ("计划调度优化Agents", "统一平台技术路线需求"): ("SR-TPT-00024", "高"),
    ("公用工程优化Agents", "碳盘查融合需求"): ("SR-TPT-00025", "高"),
    ("公用工程优化Agents", "无人调度融合需求"): ("SR-TPT-00026", "高"),
    ("换热网络评估优化Agents", "换热网络评估Agent需求"): ("SR-TPT-00027", "高"),
    ("换热网络评估优化Agents", "换热网络优化Agent需求"): ("SR-TPT-00028", "高"),
    ("智能仿真Agents", "国产化改造"): ("SR-TPT-00029", "高"),
    ("智能仿真Agents", "操作培训专家融合"): ("SR-TPT-00030", "高"),
    ("智能仿真Agents", "理论考试专家融合"): ("SR-TPT-00031", "高"),
    ("智能仿真Agents", "模型训练、混合模型生成需求"): ("SR-TPT-00032", "高"),
    ("智能仿真Agents", "工艺、规程、故障自动化组态需求"): ("SR-TPT-00033", "高"),
    ("智能仿真Agents", "仿真应用扩大需求"): ("SR-TPT-00034", "高"),
    ("智能仿真Agents", "故障模块应用需求"): ("SR-TPT-00035", "高"),
    ("智能仿真Agents", "内置模型制作对应的课件，开展线上培训内容"): ("SR-TPT-00036", "高"),
    ("非功能性需求", "轻量化部署需求"): ("SR-TPT-00037", "高"),
    ("非功能性需求", "等保与AI数据安全需求"): ("SR-TPT-00038", "高"),
    ("非功能性需求", "工程实施效率提升需求"): ("SR-TPT-00039", "高"),
    ("非功能性需求", "易用性提升需求"): ("SR-TPT-00040", "高"),
    ("非功能性需求", "agents兼容与国产化支持需求"): ("SR-TPT-00041", "高"),
}

RE_SUBTASK_PREFIX = re.compile(r"^子类：(?P<mod>[^\n]+)\n具体描述：(?P<body>[\s\S]*)$")


def find_db() -> Path:
    import os
    env = os.environ.get("DATABASE_URL", "")
    if env.startswith("sqlite:///"):
        p = Path(env.replace("sqlite:///", ""))
        if p.exists():
            return p
    for d in CANDIDATE_DIRS:
        for name in DB_FILENAMES:
            p = Path(d) / name
            if p.exists():
                return p
    for name in DB_FILENAMES:
        p = Path(name)
        if p.exists():
            return p
    print("!! 未找到 database_prod.sqlite / database.sqlite，请在 backend 目录下运行")
    sys.exit(1)


def add_columns(conn: sqlite3.Connection) -> None:
    cur = conn.execute("PRAGMA table_info(tm_tasks)")
    existing = {row[1] for row in cur.fetchall()}
    for col, ddl in NEW_COLUMNS:
        if col in existing:
            print(f"  = 列已存在：{col}")
            continue
        conn.execute(f"ALTER TABLE tm_tasks ADD COLUMN {col} {ddl}")
        print(f"  + 新增列：{col}")


def migrate_data(conn: sqlite3.Connection) -> None:
    proj = conn.execute(
        "SELECT id FROM tm_projects WHERE name = ?", (PROJECT_NAME,)
    ).fetchone()
    if not proj:
        print("  - 未找到项目「%s」，跳过数据回填" % PROJECT_NAME)
        return

    rows = conn.execute(
        "SELECT t.id, t.title, t.requirement, d.name FROM tm_tasks t "
        "LEFT JOIN tm_domains d ON d.id = t.domain_id WHERE t.project_id = ?",
        (proj[0],),
    ).fetchall()
    n_mod = n_sr = 0
    for tid, title, requirement, domain_name in rows:
        req = requirement or ""
        module = ""
        body = req
        m = RE_SUBTASK_PREFIX.match(req)
        if m:
            module = m.group("mod").strip()
            body = m.group("body").strip()
        sr_code, priority = SRS_META.get((domain_name or "", title), ("", ""))
        if module or body != req or sr_code:
            conn.execute(
                "UPDATE tm_tasks SET module = ?, requirement = ?, sr_code = ?, "
                "priority = ? WHERE id = ?",
                (module, body, sr_code, priority, tid),
            )
            if module:
                n_mod += 1
            if sr_code:
                n_sr += 1
    print(f"  + 回填 module：{n_mod} 条；回填 sr_code/priority：{n_sr} 条")

    # 其他项目：仅提取「子类：」前缀（如有）
    others = conn.execute(
        "SELECT id, requirement FROM tm_tasks WHERE project_id != ? AND requirement LIKE '子类：%'",
        (proj[0],),
    ).fetchall()
    for tid, req in others:
        m = RE_SUBTASK_PREFIX.match(req or "")
        if m:
            conn.execute(
                "UPDATE tm_tasks SET module = ?, requirement = ? WHERE id = ?",
                (m.group("mod").strip(), m.group("body").strip(), tid),
            )
    print(f"  + 其他项目提取 module：{len(others)} 条")


def main() -> None:
    db_path = find_db()
    print(f"== tm_tasks 字段迁移：{db_path} ==")
    # 备份
    bak = db_path.with_suffix(".sqlite.bak_taskfields")
    if not bak.exists():
        import shutil
        shutil.copy2(db_path, bak)
        print(f"  + 已备份 → {bak.name}")
    else:
        print(f"  = 备份已存在：{bak.name}")

    conn = sqlite3.connect(db_path)
    try:
        add_columns(conn)
        migrate_data(conn)
        conn.commit()
        print("== 完成 ==")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
