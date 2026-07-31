"""
将真实测试计划灌入本地 database_dev（合并版：大 Task + 原小项作 Action）。

用法（在 backend 目录）：
    python scripts/seed_real_test_plan.py

规则：
- 相近小项合并成大 Task；原表一行小项 → 本周一条 Action
- 用户名=拼音，密码=123456；hj / xiaojun 复用
- 原表划掉/无人：Action 负责人回落到 Task 测试负责人（满足 A1）；账号「无」仅占位展示且禁止登录
- 每次运行会清空项目「TPT v2.1」旧 Task/Action，并清空推送快照/幂等记录（避免旧 Action id 导致下次日报全是「新增」）
"""
from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.auth.models import User, UserRole
from app.auth.service import hash_password
from app.platform.database import SessionLocal
from app.test_manage.config import (
    PROJECT_STATUS_ACTIVE,
    STATUS_CANCELLED,
    STATUS_DONE,
    STATUS_DRAFT,
    STATUS_PUBLISHED,
    TASK_STATUS_CANCELLED,
    TASK_STATUS_DONE,
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
)
from app.test_manage.week import current_week_start, previous_week_start, week_end, week_key

DEFAULT_PASSWORD = "123456"
PROJECT_NAME = "TPT v2.1"
SEED_MARKER = "seed:merged-task-action-2026-07"

UNASSIGNED_CN = "无"
UNASSIGNED_USERNAME = "无"

NAME_TO_USER = {
    "无": UNASSIGNED_USERNAME,
    "黄婧": "hj",
    "袁小君": "xiaojun",
    "郑志方": "zhengzhifang",
    "叶学武": "yexuewu",
    "刘义斌": "liuyibin",
    "丁乔": "dingqiao",
    "张雪": "zhangxue",
    "刘震": "liuzhen",
    "尤佳欣": "youjiaxin",
    "吴鼎": "wuding",
    "刘佳": "liujia",
    "袁琦": "yuanqi",
    "刘洁": "liujie",
    "叶学莉": "yexueli",
    "张雯": "zhangwen",
    "徐文耀": "xuwenyao",
    "尤勇": "youyong",
    "张莹": "zhangying",
    "吴萧": "wuxiao",
    "孙厚凯": "sunhoukai",
    "李莉萍": "liliping",
    "李和海": "lihehai",
    "孙瑜": "sunyu",
    "刘灏": "liuhao",
    "夏嘉": "xiajia",
    "童霜": "tongshuang",
}


@dataclass
class WeekProg:
    note: str
    percent: int
    risk: str = ""


@dataclass
class ChildAction:
    """原表一行小项 → 大 Task 下的一条 Action。"""

    title: str
    people: list[str]
    requirement: str = ""
    # published / done / cancelled / draft → 映射到 Action.status
    kind: str = "published"
    weeks: list[WeekProg] = field(default_factory=list)


@dataclass
class MegaTask:
    title: str
    domain: str
    requirement: str
    people: list[str]
    task_status: str
    children: list[ChildAction]


def _people(names: list[str] | None) -> list[str]:
    out = [n.strip() for n in (names or []) if n and str(n).strip()]
    return out if out else [UNASSIGNED_CN]


def _latest(weeks: list[WeekProg]) -> WeekProg:
    if not weeks:
        return WeekProg("", 0)
    return weeks[-1]


def _action_status(kind: str, prog: WeekProg) -> str:
    if kind == "draft":
        return STATUS_DRAFT
    if kind == "cancelled":
        return STATUS_CANCELLED
    if kind == "done" or prog.percent >= 100:
        return STATUS_DONE
    return STATUS_PUBLISHED


def _rows() -> list[MegaTask]:
    """
    合并草案（约 10 个大 Task）：相近小项收拢，原小项作 Action。
    """
    return [
        MegaTask(
            title="0507 版本交付测试",
            domain="交付",
            requirement="0507 主版本 / ARM / 安装包 / camp 升级与安装工具等相关交付验证",
            people=["郑志方", "叶学武", "刘义斌", "丁乔", "张雪", "刘震", "尤佳欣", "吴鼎", "吴萧", "张雯"],
            task_status=TASK_STATUS_PUBLISHED,
            children=[
                ChildAction(
                    "0507主版本测试",
                    ["郑志方", "叶学武", "刘义斌", "丁乔", "张雪", "刘震", "尤佳欣"],
                    "前后端异步改造冒烟；大文件；提示意图",
                    "done",
                    [
                        WeekProg("主版本冒烟推进", 70),
                        WeekProg("大文件与意图测试完成", 90),
                        WeekProg("0507主版本测试完成", 100),
                    ],
                ),
                ChildAction(
                    "ARM版本测试",
                    ["郑志方", "叶学武", "刘义斌", "丁乔", "张雪", "刘震", "尤佳欣"],
                    "对照0507主版本冒烟（无 GPU）",
                    "done",
                    [
                        WeekProg("ARM 冒烟启动", 50),
                        WeekProg("对照主版本回归", 85),
                        WeekProg("ARM 版本测试完成", 100),
                    ],
                ),
                ChildAction(
                    "camp环境0507版本升级测试",
                    ["张雯", "刘洁", "袁琦", "袁小君", "徐文耀", "尤勇"],
                    "camp 环境 0507 升级冒烟",
                    "done",
                    [
                        WeekProg("升级准备", 40),
                        WeekProg("冒烟执行", 80),
                        WeekProg("升级测试完成", 100),
                    ],
                ),
                ChildAction(
                    "0507版本安装包测试",
                    ["吴萧"],
                    "0507 安装包验证",
                    "done",
                    [
                        WeekProg("安装包冒烟", 60),
                        WeekProg("测试完成", 100),
                        WeekProg("已完成", 100),
                    ],
                ),
                ChildAction(
                    "安装工具测试",
                    ["刘义斌"],
                    "多架构安装工具验证",
                    "published",
                    [
                        WeekProg("无机器可用", 20, "无机器可用"),
                        WeekProg("ARM 机器安装失败", 40, "ARM 机器安装失败"),
                        WeekProg("虚拟机安装与服务异常排查中", 60, "安装失败/服务拉起异常，需回归"),
                    ],
                ),
                ChildAction(
                    "细颗粒测试",
                    ["郑志方", "吴鼎"],
                    "组态 agent 功能",
                    "cancelled",
                    [
                        WeekProg("组态验证中", 40, "需求变更，任务挂起"),
                        WeekProg("挂起中，等待排期", 40, "挂起"),
                        WeekProg("仍挂起", 40, "挂起"),
                    ],
                ),
            ],
        ),
        MegaTask(
            title="Agent 平台能力",
            domain="Agent",
            requirement="自定义 Agent / Skill / 应用关联 / 我的 Agent / 报表接口 / 提炼网络等平台侧能力",
            people=["袁小君", "黄婧", "尤佳欣", "刘洁"],
            task_status=TASK_STATUS_PUBLISHED,
            children=[
                ChildAction(
                    "自定义Agent",
                    ["袁小君"],
                    "自主 Agent / SKILL / 定时任务",
                    "published",
                    [
                        WeekProg("一轮完成，等待能力对齐", 60),
                        WeekProg("发布功能一轮完成，遗留 15 个 bug", 75, "遗留 15 个 bug"),
                        WeekProg("除条件触发外基本完成，遗留 8 个 bug", 80, "遗留 8 个 bug"),
                    ],
                ),
                ChildAction(
                    "应用关联自主Agent与应用生成",
                    ["袁小君"],
                    "应用关联自主 Agent 对话",
                    "draft",
                    [],
                ),
                ChildAction(
                    "平台开发-我的Agent",
                    ["黄婧"],
                    "Agent/Skill 安全与权限约束",
                    "done",
                    [
                        WeekProg("一轮完成，缺陷待修", 70, "缺陷待修"),
                        WeekProg("测试完成", 100),
                        WeekProg("已完成归档", 100),
                    ],
                ),
                ChildAction(
                    "统计报表Agent接口自定义明细",
                    ["尤佳欣"],
                    "统计报表 Agent 接口自定义明细",
                    "done",
                    [
                        WeekProg("接口联调", 70),
                        WeekProg("测试完成", 100),
                        WeekProg("已完成", 100),
                    ],
                ),
                ChildAction(
                    "提炼网络",
                    ["刘洁"],
                    "评估 Agent、模型部署、站域网络等",
                    "done",
                    [
                        WeekProg("评估推进中", 60),
                        WeekProg("测试完成，整理测试记录", 100),
                        WeekProg("已完成", 100),
                    ],
                ),
            ],
        ),
        MegaTask(
            title="业务 Agents 专项",
            domain="Agent",
            requirement="设备健康 / 报警管理 / 操作导引 / 网络优化 / 智能控制等业务 Agent",
            people=["袁小君", "徐文耀", "孙厚凯", "童霜", "刘灏"],
            task_status=TASK_STATUS_PUBLISHED,
            children=[
                ChildAction(
                    "设备健康agent测试",
                    ["袁小君", "徐文耀"],
                    "仪控/腐蚀/电磁阀/动设备健康监测",
                    "published",
                    [
                        WeekProg("一轮 90%，test 环境不稳", 90, "test 环境不稳定"),
                        WeekProg("data-hub link 数据未上送", 90, "data-hub link 数据未上送"),
                        WeekProg("一轮完成，遗留缺陷跟进", 92, "遗留缺陷待关闭"),
                    ],
                ),
                ChildAction(
                    "报警管理Agents测试",
                    ["孙厚凯"],
                    "TPT 整合；DataHub；skill；x86",
                    "published",
                    [
                        WeekProg("测试完成，记录整理中", 85),
                        WeekProg("45 环境冒烟", 90),
                        WeekProg("修复同步/角色/附件问题；45 基本通过", 95),
                    ],
                ),
                ChildAction(
                    "操作导引Agents测试",
                    ["童霜"],
                    "TPT 整合；DataHub；x86（原表非 hj）",
                    "published",
                    [
                        WeekProg("direct 脚本数据问题，集成失败", 50, "direct 脚本数据问题，集成失败"),
                        WeekProg("等待开发改 bug", 60, "等待开发改 bug"),
                        WeekProg("UI 已测；数据读写未解决", 80, "数据读写问题尚未解决"),
                    ],
                ),
                ChildAction(
                    "网络优化agent测试",
                    ["袁小君"],  # 原表「黄婧」已划掉 → 由 Task 负责人挂名
                    "网络优化 Agent（原负责人已划掉，待正式认领）",
                    "published",
                    [
                        WeekProg("进度完成 80%", 80),
                        WeekProg("约 95%，bug 修复验证", 95),
                        WeekProg(
                            "一轮完成；datahub 历史读取有问题",
                            80,
                            "原负责人已划掉待认领；datahub 历史读取有问题，需二轮测试",
                        ),
                    ],
                ),
                ChildAction(
                    "智能控制agent融合测试",
                    ["刘灏"],
                    "脚本/模型辨识/DataHub/K8s 等",
                    "published",
                    [
                        WeekProg("本周未进行", 40),
                        WeekProg("6 月项推进；7 月脚本/模型辨识测试中", 70),
                        WeekProg("模型辨识优化未合入", 80, "模型辨识优化未合入"),
                    ],
                ),
            ],
        ),
        MegaTask(
            title="平台 AI / LLM",
            domain="平台",
            requirement="LLM 记忆/多 Agent/边云协同与数据中心增强",
            people=["黄婧", "袁琦"],
            task_status=TASK_STATUS_PUBLISHED,
            children=[
                ChildAction(
                    "LLM功能",
                    ["黄婧"],
                    "记忆/上下文/multi-agent/边云协同",
                    "done",
                    [
                        WeekProg("memory&multiagent 基本完成，遗留 bug", 90, "尚有一个 bug 待回归"),
                        WeekProg("harness 相关 bug 已关闭", 100),
                        WeekProg("LLM 功能测试完成", 100),
                    ],
                ),
                ChildAction(
                    "数据中心增强",
                    ["袁琦"],
                    "数据中心增强与 PRIDE 对接",
                    "published",
                    [
                        WeekProg("PRIDE 对接问题跟踪", 40, "PRIDE 对接异常"),
                        WeekProg("继续跟进 PRIDE 集成", 55, "PRIDE 集成未完成"),
                        WeekProg("约 70%，PRIDE 仍有阻塞", 70, "PRIDE 阻塞"),
                    ],
                ),
            ],
        ),
        MegaTask(
            title="平台数据与控制",
            domain="平台",
            requirement="下写 / OPCUA 闭环 / 模型自更新 / 长期测试 / 问数",
            people=["叶学武", "刘义斌", "丁乔", "张雪", "叶学莉", "张莹", "刘佳"],
            task_status=TASK_STATUS_PUBLISHED,
            children=[
                ChildAction(
                    "下写功能测试",
                    ["叶学武", "刘义斌", "丁乔", "张雪"],
                    "数据下写",
                    "published",
                    [
                        WeekProg("算法问题", 30, "算法问题"),
                        WeekProg("基本流程不通", 45, "基本流程不通"),
                        WeekProg("大屏算法失败已确认", 70, "大屏算法失败确认"),
                    ],
                ),
                ChildAction(
                    "应用管理配合采集器下写到OPCUA闭环控制",
                    ["叶学莉"],
                    "采集器下写 OPCUA 闭环",
                    "done",
                    [
                        WeekProg("联调中", 50),
                        WeekProg("闭环验证通过", 100),
                        WeekProg("已完成", 100),
                    ],
                ),
                ChildAction(
                    "模型自更新功能测试",
                    ["叶学武", "刘义斌", "丁乔"],
                    "定时模型更新；Agent 自动更新",
                    "published",
                    [
                        WeekProg("定时更新能力验证", 40),
                        WeekProg("Agent 自动更新异常", 55, "Agent 自动更新异常"),
                        WeekProg("Agent 自动更新未闭环", 70, "Agent 自动更新未闭环"),
                    ],
                ),
                ChildAction(
                    "长期测试",
                    ["叶学武", "刘义斌", "丁乔", "张莹"],
                    "长期稳定性",
                    "done",
                    [
                        WeekProg("长期压测执行", 80),
                        WeekProg("测试完成", 100),
                        WeekProg("已完成", 100),
                    ],
                ),
                ChildAction(
                    "问数功能回归",
                    ["刘佳"],
                    "pride/apc/pid/aas/direct 接入与问数评估",
                    "published",
                    [
                        WeekProg("APC bug 回归", 50, "APC 回归缺陷"),
                        WeekProg("AAS 一轮完成；direct/pride 接入中", 70),
                        WeekProg("direct 一轮完成，pride 仍在测", 80),
                    ],
                ),
            ],
        ),
        MegaTask(
            title="平台交互与工具",
            domain="平台",
            requirement="HMI / 排队超时 / 数据查询 / 国际化 / MinIO",
            people=["袁小君", "丁乔", "张莹"],
            task_status=TASK_STATUS_PUBLISHED,
            children=[
                ChildAction(
                    "HMI流程库管理界面",
                    ["袁小君"],
                    "HMI 文件夹 CRUD",
                    "done",
                    [WeekProg("CRUD 验证", 70), WeekProg("测试完成", 100), WeekProg("已完成", 100)],
                ),
                ChildAction(
                    "算法排队超时交互功能",
                    ["丁乔"],
                    "SCOPE GUI 排队超时交互",
                    "done",
                    [WeekProg("交互验证", 80), WeekProg("测试完成", 100), WeekProg("已完成", 100)],
                ),
                ChildAction(
                    "数据查询功能",
                    ["张莹"],
                    "数据查询三期与版本部署",
                    "done",
                    [
                        WeekProg("三期测试推进", 70),
                        WeekProg("三期完成，版本已部署", 100),
                        WeekProg("已完成", 100),
                    ],
                ),
                ChildAction(
                    "国际化测试",
                    ["张莹"],
                    "国际化能力",
                    "draft",
                    [WeekProg("未开始", 0, "缺少测试环境")],
                ),
                ChildAction(
                    "代替MinIO专项测试",
                    ["袁小君"],  # 原表无参与人员 → Task 负责人挂名；已取消仅本周一条
                    "文件存储冒烟（原表无参与人员）",
                    "cancelled",
                    [],
                ),
            ],
        ),
        MegaTask(
            title="评估需求包",
            domain="平台",
            requirement="5/6 月评估与运行控制相关草稿项",
            people=["尤佳欣", "张莹", "张雯"],
            task_status=TASK_STATUS_PUBLISHED,
            children=[
                ChildAction(
                    "5月评估新需求",
                    ["尤佳欣", "张莹"],
                    "5 月评估新需求",
                    "done",
                    [WeekProg("需求用例执行", 60), WeekProg("测试完成", 100), WeekProg("已完成", 100)],
                ),
                ChildAction(
                    "6月评估需求测试",
                    ["尤佳欣"],
                    "6 月评估验收",
                    "done",
                    [
                        WeekProg("高级参数与大屏仍在跑", 80),
                        WeekProg("2 个功能未提交", 90),
                        WeekProg("已测试完成", 100),
                    ],
                ),
                ChildAction(
                    "运行控制闭环任务过多导致算法被取消发布",
                    ["张雯"],
                    "重构版本；问题修改回归",
                    "draft",
                    [],
                ),
            ],
        ),
        MegaTask(
            title="客户定制交付",
            domain="定制",
            requirement="离博 / 兴园 / 无人调度 / 无人驾驶 / 管网等定制（部分不入 7 月产品包）",
            people=["叶学莉", "尤佳欣", "李莉萍", "李和海", "孙瑜"],
            task_status=TASK_STATUS_PUBLISHED,
            children=[
                ChildAction(
                    "离博原油合规监控定制",
                    ["叶学莉"],
                    "合规监控定制验收",
                    "done",
                    [WeekProg("定制联调", 80), WeekProg("验收通过", 100), WeekProg("已完成", 100)],
                ),
                ChildAction(
                    "兴园报警使能定制",
                    ["尤佳欣"],
                    "报警使能定制",
                    "done",
                    [WeekProg("功能验证", 90), WeekProg("测试完成", 100), WeekProg("已完成", 100)],
                ),
                ChildAction(
                    "无人调度TPT整合改造",
                    ["李莉萍"],
                    "定制（不放入 7 月产品包）",
                    "published",
                    [
                        WeekProg("数据卡住", 40, "数据卡住"),
                        WeekProg("pilot 数据不全", 60, "pilot 数据不全"),
                        WeekProg("上周未进行，后续继续", 80),
                    ],
                ),
                ChildAction(
                    "无人驾驶TPT融合改造",
                    ["李和海"],
                    "定制（不放入 7 月产品包）",
                    "published",
                    [
                        WeekProg("预警卡住", 40, "预警卡住"),
                        WeekProg("pilot 数据不全", 60, "pilot 数据不全"),
                        WeekProg("后续在 nbp-test 测试", 80),
                    ],
                ),
                ChildAction(
                    "管网融合",
                    ["孙瑜"],
                    "定制（不放入 7 月产品包）",
                    "published",
                    [
                        WeekProg("剩余 7 个问题", 70, "剩余 7 个问题"),
                        WeekProg("剩余 3 个 BUG", 80, "剩余 3 个 BUG"),
                        WeekProg("上周未进行", 80),
                    ],
                ),
            ],
        ),
    ]


def ensure_user(db: Session, username: str, real_name: str = "") -> User:
    row = db.query(User).filter(User.username == username).first()
    if row:
        if real_name and (row.real_name or "").strip() != real_name:
            row.real_name = real_name
        return row
    row = User(
        username=username,
        password_hash=hash_password(DEFAULT_PASSWORD),
        role=UserRole.Engineer,
        real_name=real_name or "",
    )
    db.add(row)
    db.flush()
    print(f"  + user {username} ({real_name or '-'})")
    return row


def ensure_project(db: Session, admin: User) -> TmProject:
    row = db.query(TmProject).filter(TmProject.name == PROJECT_NAME).first()
    if row:
        return row
    row = TmProject(
        name=PROJECT_NAME,
        description="合并版测试计划：大 Task + 原小项 Action",
        status=PROJECT_STATUS_ACTIVE,
        created_by=admin.id,
    )
    db.add(row)
    db.flush()
    print(f"  + project {PROJECT_NAME}")
    return row


def ensure_domain(db: Session, project: TmProject, name: str, sort_order: int) -> TmDomain:
    row = (
        db.query(TmDomain)
        .filter(TmDomain.project_id == project.id, TmDomain.name == name)
        .first()
    )
    if row:
        return row
    row = TmDomain(project_id=project.id, name=name, sort_order=sort_order)
    db.add(row)
    db.flush()
    print(f"  + domain {name}")
    return row


def wipe_project_tree(db: Session, project: TmProject) -> None:
    """清空该项目下全部 Task/Action（保留项目与领域），并重置推送快照以免旧 id 污染。"""
    tasks = db.query(TmTask).filter(TmTask.project_id == project.id).all()
    task_ids = [t.id for t in tasks]
    if not task_ids:
        print("  (no old tasks)")
    else:
        actions = db.query(TmAction).filter(TmAction.project_id == project.id).all()
        action_ids = [a.id for a in actions]
        if action_ids:
            db.query(TmDailyUpdate).filter(TmDailyUpdate.action_id.in_(action_ids)).delete(
                synchronize_session=False
            )
            db.query(TmActionCorrection).filter(
                TmActionCorrection.action_id.in_(action_ids)
            ).delete(synchronize_session=False)
            db.query(TmAction).filter(TmAction.project_id == project.id).delete(
                synchronize_session=False
            )
        db.query(TmTaskUpdateLog).filter(TmTaskUpdateLog.task_id.in_(task_ids)).delete(
            synchronize_session=False
        )
        db.query(TmTaskTester).filter(TmTaskTester.task_id.in_(task_ids)).delete(
            synchronize_session=False
        )
        db.query(TmTask).filter(TmTask.project_id == project.id).delete(synchronize_session=False)
        print(f"  wiped tasks={len(task_ids)} actions={len(action_ids)}")

    # 灌数会换新 Action UUID；不清快照会让下次日报把全部风险当成「新增」
    snap_n = db.query(TmPushSnapshot).delete(synchronize_session=False)
    run_n = db.query(TmPushRun).delete(synchronize_session=False)
    print(f"  wiped push snapshots={snap_n} runs={run_n}")


def create_mega_task(
    db: Session,
    *,
    project: TmProject,
    domain: TmDomain,
    creator: User,
    mega: MegaTask,
    users_by_name: dict[str, User],
) -> TmTask:
    people = _people(mega.people)
    lead = users_by_name[people[0]]
    task = TmTask(
        project_id=project.id,
        domain_id=domain.id,
        title=mega.title,
        requirement=mega.requirement or "",
        lead_id=lead.id,
        status=mega.task_status,
        created_by=creator.id,
        published_at=now_tm() if mega.task_status != "draft" else None,
    )
    db.add(task)
    db.flush()
    for name in people[1:]:
        if name == UNASSIGNED_CN:
            continue
        u = users_by_name[name]
        if u.id == lead.id:
            continue
        db.add(TmTaskTester(task_id=task.id, user_id=u.id))

    db.add(
        TmTaskUpdateLog(
            task_id=task.id,
            user_id=creator.id,
            summary="合并灌数：大 Task + 原小项 Action",
            detail=f"{SEED_MARKER}\nchildren={len(mega.children)}",
        )
    )
    print(f"  + task [{mega.domain}] {mega.title} ({len(mega.children)} actions)")
    return task


def create_child_actions(
    db: Session,
    *,
    task: TmTask,
    mega: MegaTask,
    creator: User,
    users_by_name: dict[str, User],
) -> int:
    """
    每个原小项 → 最近最多 3 周各一条 Action（有周进度才建；无周进度的草稿/挂起仅建本周一条）。
    cancelled：仅本周一条，避免噪音多周。
    原表「无」负责人：回落到 Task lead（A1）。
    """
    week_starts = [
        previous_week_start(previous_week_start(current_week_start())),
        previous_week_start(current_week_start()),
        current_week_start(),
    ]
    lead_user = next((u for u in users_by_name.values() if u.id == task.lead_id), None)
    n = 0
    for child in mega.children:
        people = _people(child.people)
        owner_name = people[0] if people else UNASSIGNED_CN
        if owner_name == UNASSIGNED_CN:
            if lead_user is None:
                raise RuntimeError(f"Task {task.title} 无 lead，无法回落负责人")
            owner = lead_user
        else:
            owner = users_by_name[owner_name]

        # 已取消：仅本周一条
        if child.kind == "cancelled":
            ws = week_starts[-1]
            action = TmAction(
                task_id=task.id,
                project_id=task.project_id,
                domain_id=task.domain_id,
                week_start=ws,
                week_key=week_key(ws),
                title=child.title,
                owner_id=owner.id,
                test_content=(child.requirement or "")[:1000],
                environment="",
                status=STATUS_CANCELLED,
                created_by=creator.id,
                published_at=None,
                due_at=week_end(ws),
            )
            db.add(action)
            n += 1
            continue

        weeks = list(child.weeks)
        if not weeks:
            # 无周进度：仅本周一条
            ws = week_starts[-1]
            st = _action_status(child.kind, WeekProg("", 0))
            action = TmAction(
                task_id=task.id,
                project_id=task.project_id,
                domain_id=task.domain_id,
                week_start=ws,
                week_key=week_key(ws),
                title=child.title,
                owner_id=owner.id,
                test_content=(child.requirement or "")[:1000],
                environment="",
                status=st,
                created_by=creator.id,
                published_at=now_tm() if st != STATUS_DRAFT else None,
                due_at=week_end(ws),
            )
            db.add(action)
            n += 1
            continue

        while len(weeks) < 3:
            weeks.insert(0, WeekProg("", 0))
        weeks = weeks[-3:]
        for ws, prog in zip(week_starts, weeks):
            # 中间空周跳过
            if not prog.note and prog.percent == 0 and child.kind not in ("cancelled",):
                # 若三周都空则上面分支已处理；有部分周数据时跳过空周
                if child.kind == "draft":
                    continue
                # 仍为占位空周则跳过
                if prog.percent == 0 and not prog.risk:
                    continue
            st = _action_status(child.kind, prog)
            action = TmAction(
                task_id=task.id,
                project_id=task.project_id,
                domain_id=task.domain_id,
                week_start=ws,
                week_key=week_key(ws),
                title=child.title,
                owner_id=owner.id,
                test_content=(prog.note or child.requirement or "")[:1000],
                environment="qa",
                status=st,
                created_by=creator.id,
                published_at=now_tm() if st not in (STATUS_DRAFT, STATUS_CANCELLED) else None,
                due_at=week_end(ws),
            )
            db.add(action)
            db.flush()
            n += 1
            if st in (STATUS_DRAFT, STATUS_CANCELLED):
                continue
            if prog.percent > 0 or prog.note or prog.risk:
                report_day = (week_end(ws) - timedelta(days=1)).date()
                if report_day > date.today():
                    report_day = date.today()
                db.add(
                    TmDailyUpdate(
                        action_id=action.id,
                        user_id=owner.id,
                        report_date=report_day,
                        progress_percent=max(0, min(100, prog.percent)),
                        risk_blocker=(prog.risk or "")[:1000],
                        progress_note=(prog.note or "")[:1000],
                    )
                )
    return n


def seed_real_test_plan() -> None:
    db = SessionLocal()
    try:
        print("== seed merged plan (大 Task + 小项 Action) ==")
        admin = db.query(User).filter(User.username == "admin").first()
        if not admin:
            raise RuntimeError("缺少 admin，请先启动后端完成 bootstrap")

        users_by_name: dict[str, User] = {}
        for cn, uname in NAME_TO_USER.items():
            users_by_name[cn] = ensure_user(db, uname, real_name=cn)

        project = ensure_project(db, admin)
        wipe_project_tree(db, project)

        domain_order = {"平台": 1, "Agent": 2, "交付": 3, "定制": 4}
        domains = {
            name: ensure_domain(db, project, name, order)
            for name, order in domain_order.items()
        }

        action_total = 0
        for mega in _rows():
            domain = domains.get(mega.domain) or domains["平台"]
            task = create_mega_task(
                db,
                project=project,
                domain=domain,
                creator=admin,
                mega=mega,
                users_by_name=users_by_name,
            )
            action_total += create_child_actions(
                db,
                task=task,
                mega=mega,
                creator=admin,
                users_by_name=users_by_name,
            )

        db.commit()
        n_tasks = db.query(TmTask).filter(TmTask.project_id == project.id).count()
        n_actions = db.query(TmAction).filter(TmAction.project_id == project.id).count()
        print(f"== done: mega_tasks={n_tasks}, actions={n_actions} (created≈{action_total}) ==")
        print("打开「本周大屏」看：左边是大 Task，展开后是原来的小项 Action。")
        print("账号示例: hj / tongshuang / xiaojun ，密码 123456")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_real_test_plan()
