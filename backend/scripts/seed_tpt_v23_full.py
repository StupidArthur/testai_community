"""
TPT v2.3 产品包需求 Excel 全量导入（含需求属性扩展字段）。

数据源：Excel「产品包需求」sheet，41 条 SR，每行一个系统需求。
导入内容：项目 → 域（大类） → Task（系统需求），含
  SR编号 / 关联IR编号 / 子类模块 / 需求类型 / 优先级 / 变更标识 /
  验收标准 / 验证人（按姓名匹配系统用户，匹配不到记入备注） / 备注。
Excel 中「验收标准/验证时间/验证结果/备注」目前全为空，导入后可在页面补充。

替换式导入：项目已存在时清空该项目下 Task/Action/日更后重建。

用法（在 backend 目录）：
    python scripts/seed_tpt_v23_full.py                      # 自动找 Excel
    python scripts/seed_tpt_v23_full.py --excel "D:\\需求.xlsx"  # 指定路径
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

try:
    from dotenv import load_dotenv
    load_dotenv(_BACKEND.parent / ".env")
    load_dotenv(_BACKEND / ".env")
except Exception:
    pass

from openpyxl import load_workbook
from sqlalchemy.orm import Session

from app.auth.models import User
from app.platform.database import SessionLocal, engine
from app.test_manage.bootstrap import _ensure_task_ext_columns
from app.test_manage.config import (
    PROJECT_STATUS_ACTIVE,
    REQ_STAGE_DEVELOPING,
    TASK_STATUS_PUBLISHED,
    now_tm,
)
from app.test_manage.models import (
    TmAction,
    TmActionCorrection,
    TmDailyUpdate,
    TmDomain,
    TmProject,
    TmPushRun,
    TmPushSnapshot,
    TmTask,
    TmTaskTester,
    TmTaskUpdateLog,
    TmTaskWeekProgress,
)

PROJECT_NAME = "TPT v2.3 产品包"
LEAD_USERNAME = "zhengzhifang"
SHEET_NAME = "产品包需求"

# Excel 列索引（0 基，跳过前 3 行表头）
COL = {
    "ir_no": 0,        # 初始需求编号
    "submitter": 1,    # 需求提交人
    "ir_name": 2,      # 初始需求名称
    "sr_no": 4,        # 系统需求编号
    "rel_ir": 5,       # 关联初始需求编号
    "domain": 6,       # 大类
    "module": 7,       # 子类/模块
    "title": 8,        # 系统需求名称
    "desc": 9,         # 系统需求描述
    "req_type": 10,    # 需求类型
    "priority": 11,    # 优先级排序
    "change_flag": 12, # 变更标识
    "done_state": 13,  # 完成情况
    "acceptance": 14,  # 验收标准
    "verifier": 15,    # 验证人
    "verified_at": 16, # 验证时间
    "verify_result": 17,  # 需求验证是否通过
    "remark": 18,      # 备注
}

EXCEL_CANDIDATES = [
    Path(__file__).resolve().parent / "TPT V2.3 产品包需求.xlsx",
    Path.home() / "Documents" / "TPT V2.3 产品包需求.xlsx",
    Path("D:/TPT V2.3 产品包需求.xlsx"),
    Path("D:/testai_community_prod/backend/TPT V2.3 产品包需求.xlsx"),
]


def find_excel(explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit)
        if p.exists():
            return p
        raise SystemExit(f"Excel 不存在：{p}")
    for p in EXCEL_CANDIDATES:
        if p.exists():
            return p
    raise SystemExit(
        "未找到 TPT V2.3 产品包需求.xlsx，请用 --excel 指定路径"
    )


def _s(v) -> str:
    """单元格 → 去空格字符串；None → ''。"""
    if v is None:
        return ""
    return str(v).strip()


def _d(v):
    """单元格 → date（Excel datetime 直接取 date 部分）。"""
    if v is None or _s(v) == "":
        return None
    if hasattr(v, "date"):
        return v.date()
    return v


def read_rows(excel: Path) -> list[dict]:
    wb = load_workbook(excel, data_only=True)
    ws = wb[SHEET_NAME]
    rows = []
    for r in ws.iter_rows(min_row=4, values_only=True):
        sr_no = _s(r[COL["sr_no"]])
        title = _s(r[COL["title"]])
        if not sr_no.startswith("SR-") or not title:
            continue  # 跳过空行/表头残留
        rows.append({
            "sr_code": sr_no[:64],
            "ir_codes": _s(r[COL["rel_ir"]]).replace("\n", "，")[:256],
            "domain": _s(r[COL["domain"]]),
            "module": _s(r[COL["module"]])[:100] or "未分类",
            "title": title[:300],
            "requirement": _s(r[COL["desc"]])[:2000],
            "req_type": _s(r[COL["req_type"]])[:32],
            "priority": _s(r[COL["priority"]])[:16],
            "change_flag": _s(r[COL["change_flag"]])[:32],
            "done_state": _s(r[COL["done_state"]]),
            "acceptance": _s(r[COL["acceptance"]])[:4000],
            "verifier_name": _s(r[COL["verifier"]]),
            "verified_at": _d(r[COL["verified_at"]]),
            "verify_result": _s(r[COL["verify_result"]])[:16],
            "remark": _s(r[COL["remark"]])[:4000],
        })
    if not rows:
        raise SystemExit(f"未从 {excel} 读到任何 SR 数据行")
    return rows


def _wipe_project_tree(db: Session, project: TmProject) -> None:
    """清空项目下所有Task/Action/日更等（重建用）。"""
    tasks = db.query(TmTask).filter(TmTask.project_id == project.id).all()
    tids = [t.id for t in tasks]
    actions = db.query(TmAction).filter(TmAction.project_id == project.id).all()
    aids = [a.id for a in actions]
    if aids:
        db.query(TmDailyUpdate).filter(TmDailyUpdate.action_id.in_(aids)).delete(synchronize_session=False)
        db.query(TmActionCorrection).filter(TmActionCorrection.action_id.in_(aids)).delete(synchronize_session=False)
        db.query(TmAction).filter(TmAction.id.in_(aids)).update({TmAction.source_action_id: None}, synchronize_session=False)
        db.query(TmAction).filter(TmAction.id.in_(aids)).delete(synchronize_session=False)
    if tids:
        db.query(TmTaskWeekProgress).filter(TmTaskWeekProgress.task_id.in_(tids)).delete(synchronize_session=False)
        db.query(TmTaskUpdateLog).filter(TmTaskUpdateLog.task_id.in_(tids)).delete(synchronize_session=False)
        db.query(TmTaskTester).filter(TmTaskTester.task_id.in_(tids)).delete(synchronize_session=False)
        db.query(TmTask).filter(TmTask.id.in_(tids)).delete(synchronize_session=False)
    db.query(TmPushSnapshot).delete(synchronize_session=False)
    db.query(TmPushRun).delete(synchronize_session=False)
    db.query(TmDomain).filter(TmDomain.project_id == project.id).delete(synchronize_session=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--excel", default=None, help="Excel 文件路径")
    args = parser.parse_args()

    excel = find_excel(args.excel)
    rows = read_rows(excel)
    print(f"== 导入 {PROJECT_NAME}（Excel 全量：{len(rows)} 条SR） ==")
    print(f"  数据源：{excel}")

    # 幂等：确保 tm_tasks 新字段列存在（老库兼容）
    _ensure_task_ext_columns(engine)

    db = SessionLocal()
    try:
        lead = db.query(User).filter(User.username == LEAD_USERNAME).first()
        if not lead:
            raise SystemExit(f"用户 {LEAD_USERNAME} 不存在，请先在用户管理创建")
        admin = db.query(User).filter(User.username == "admin").first()
        if not admin:
            raise SystemExit("admin用户不存在")

        # 验证人姓名 → 用户
        all_users = db.query(User).all()
        by_name: dict[str, User] = {}
        for u in all_users:
            if u.real_name and u.real_name.strip():
                by_name.setdefault(u.real_name.strip(), u)
        unmatched_verifiers: set[str] = set()
        n_matched = 0

        proj = db.query(TmProject).filter(TmProject.name == PROJECT_NAME).first()
        if not proj:
            proj = TmProject(
                name=PROJECT_NAME,
                description="TPT v2.3 产品包需求（Excel 全量导入）",
                status=PROJECT_STATUS_ACTIVE,
                created_by=admin.id,
            )
            db.add(proj)
            db.flush()
            print(f"  + 创建项目 {PROJECT_NAME}")
        else:
            _wipe_project_tree(db, proj)
            db.flush()
            print(f"  ~ 项目已存在，已清空旧数据")

        # 域 = 大类（按SR数量降序）
        cats = sorted({r["domain"] for r in rows})
        cat_count = {c: sum(1 for r in rows if r["domain"] == c) for c in cats}
        cats.sort(key=lambda c: -cat_count[c])
        domains: dict[str, TmDomain] = {}
        for i, c in enumerate(cats):
            d = TmDomain(project_id=proj.id, name=c, sort_order=i + 1)
            db.add(d)
            db.flush()
            domains[c] = d
        print(f"  + 创建 {len(domains)} 个域：{cats}")

        n_task = 0
        for r in rows:
            # 验证人：匹配到用户 → verifier_id；匹配不到 → 记入备注
            verifier = by_name.get(r["verifier_name"]) if r["verifier_name"] else None
            remark = r["remark"]
            if r["verifier_name"] and not verifier:
                unmatched_verifiers.add(r["verifier_name"])
                note = f"验证人：{r['verifier_name']}"
                remark = f"{remark}\n{note}".strip() if remark else note
            elif verifier:
                n_matched += 1

            task = TmTask(
                project_id=proj.id,
                domain_id=domains[r["domain"]].id,
                title=r["title"],
                requirement=r["requirement"],
                sr_code=r["sr_code"],
                ir_codes=r["ir_codes"],
                module=r["module"],
                req_type=r["req_type"],
                priority=r["priority"],
                change_flag=r["change_flag"],
                acceptance_criteria=r["acceptance"],
                verifier_id=verifier.id if verifier else None,
                verified_at=r["verified_at"],
                verify_result=r["verify_result"],
                remark=remark,
                subtasks=[],
                lead_id=lead.id,
                status=TASK_STATUS_PUBLISHED,
                req_stage=REQ_STAGE_DEVELOPING,
                created_by=admin.id,
                published_at=now_tm(),
            )
            db.add(task)
            db.flush()
            db.add(TmTaskUpdateLog(
                task_id=task.id,
                user_id=admin.id,
                summary="导入：TPT v2.3 产品包需求（Excel全量）",
                detail=f"seed_tpt_v23_full | {r['sr_code']}",
            ))
            n_task += 1

        db.commit()
        print(f"\n  导入完成：{n_task} 个Task，{len(domains)} 个域")
        print(f"  验证人匹配用户：{n_matched} 条")
        if unmatched_verifiers:
            print(f"  ! 以下验证人未匹配到系统用户（已记入备注）：{sorted(unmatched_verifiers)}")
        print(f"  项目：{PROJECT_NAME}｜负责人：{lead.real_name} (@{lead.username})")
    finally:
        db.close()


if __name__ == "__main__":
    main()
