"""
tool_hub 启动：预置平台工具（AI 翻译）与客户端工具（功能录制）。
"""
from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from sqlalchemy import inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.auth.models import User, UserRole
from app.platform.config import PROJECT_ROOT, TOOL_HUB_ARTIFACT_DIR

from .models import Tool, ToolVersion

_TRANSLATE_SLUG = "ai_translate"
_RECORDER_SLUG = "feature_recorder"

_RECORDER_RELEASE_ZIP = (
    PROJECT_ROOT / "feature_recorder" / "release" / "feature-recorder-win64.zip"
)

RECORDER_BUILD_HINT = (
    "功能录制安装包尚未构建或文件已丢失。"
    "请在项目根目录执行：powershell -ExecutionPolicy Bypass -File scripts\\build_feature_recorder.ps1 ，"
    "构建完成后重启后端。"
)

_TRANSLATE_MANUAL = """# AI 翻译

将 **功能录制** 产出的 ZIP 上传至平台，自动翻译为中文测试用例与文档。

## 推荐工作流

1. 工具集 → **功能录制** → 下载客户端并录制操作
2. 将 `output/run_*` 目录打包为 zip
3. 回到工具集 → **AI 翻译**（本页）→ 上传 zip
4. 等待任务完成，下载用例与 agents 等产物

## 上传步骤

1. 点击「上传 ZIP」
2. 选择录制包并填写任务名称（可选）
3. 在任务列表中查看进度与结果
4. 完成后下载翻译输出

## 说明

- 支持阶段一 / 二 / 四完整 pipeline
- 任务排队执行，可在列表页刷新状态
"""

_RECORDER_MANUAL = """# 功能录制

在真实 Chromium 浏览器中录制 UI 操作，生成可追溯的录制包（`run_*` 目录），供 **AI 翻译** 使用。

## 使用步骤

### 1. 下载并运行客户端

点击本页 **下载** 获取 `feature-recorder-win64.zip`，解压后：

- 双击 `feature-recorder.cmd` 启动本地 Dashboard（默认 `http://localhost:3000`）
- 整个解压目录需保留在一起（含 `chrome-win64` 或 `ms-playwright`）

### 2. 录制

1. 在 Dashboard 配置被测系统 URL
2. 点击开始录制，在弹出的浏览器中操作
3. 关闭浏览器窗口结束录制
4. 在 `output/run_YYYYMMDD.../` 下查看 `meta.json`、`actions/`、`snapshots/`

### 3. 交给 AI 翻译

将 `run_*` **整个目录**打成 zip，然后：

**工具集 → AI 翻译 → 上传 zip**

## 说明

- 本工具仅负责录制；翻译请在平台 **AI 翻译** 中完成
- 录制不依赖 AI API；离线 Chromium 随分发包提供
- 证据链：N 个操作对应 N+1 个页面快照，便于翻译阶段分析
"""


def _admin_user_id(db: Session) -> int:
    admin = db.query(User).filter(User.role == UserRole.Admin).first()
    return admin.id if admin else 1


def _ensure_platform_tool(
    db: Session,
    *,
    slug: str,
    display_name: str,
    link_url: str,
    manual_md: str,
    owner_id: int,
) -> None:
    tool = db.query(Tool).filter(Tool.slug == slug).first()
    if not tool:
        tool = Tool(
            slug=slug,
            display_name=display_name,
            tool_kind="platform",
            tool_type="default",
            link_url=link_url,
            owner_user_id=owner_id,
            enabled=True,
        )
        db.add(tool)
        db.flush()
        db.add(
            ToolVersion(
                tool_id=tool.id,
                version_label="1.0.0",
                manual_md=manual_md,
                changelog_md="",
                created_by_user_id=owner_id,
            )
        )
        return

    tool.display_name = display_name
    tool.link_url = link_url
    if tool.versions:
        latest = max(tool.versions, key=lambda v: v.created_at)
        latest.manual_md = manual_md


def _ensure_client_tool(
    db: Session,
    *,
    slug: str,
    display_name: str,
    manual_md: str,
    owner_id: int,
) -> Tool:
    tool = db.query(Tool).filter(Tool.slug == slug).first()
    if not tool:
        tool = Tool(
            slug=slug,
            display_name=display_name,
            tool_kind="client",
            tool_type="default",
            link_url=None,
            owner_user_id=owner_id,
            enabled=True,
        )
        db.add(tool)
        db.flush()
        db.add(
            ToolVersion(
                tool_id=tool.id,
                version_label="1.0.0",
                manual_md=manual_md,
                changelog_md="",
                created_by_user_id=owner_id,
            )
        )
    else:
        tool.display_name = display_name
        if tool.versions:
            latest = max(tool.versions, key=lambda v: v.created_at)
            latest.manual_md = manual_md
    return tool


def sync_feature_recorder_artifact(db: Session, tool: Tool, owner_id: int | None = None) -> bool:
    """
    若本地 release zip 存在，同步到工具集制品目录并绑定最新版本。

    返回：同步后制品文件是否可下载。
    """
    if tool.slug != _RECORDER_SLUG:
        return False

    latest = max(tool.versions, key=lambda v: (v.created_at, v.version_label)) if tool.versions else None
    if latest and latest.artifact_stored_name:
        dest = TOOL_HUB_ARTIFACT_DIR / latest.artifact_stored_name
        if dest.is_file():
            return True

    if not _RECORDER_RELEASE_ZIP.is_file():
        return False

    TOOL_HUB_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    oid = owner_id if owner_id is not None else _admin_user_id(db)

    if latest and latest.artifact_stored_name:
        dest = TOOL_HUB_ARTIFACT_DIR / latest.artifact_stored_name
        shutil.copy2(_RECORDER_RELEASE_ZIP, dest)
        latest.artifact_filename = "feature-recorder-win64.zip"
        return dest.is_file()

    stored_name = f"{tool.id}_{uuid.uuid4().hex}.zip"
    dest = TOOL_HUB_ARTIFACT_DIR / stored_name
    shutil.copy2(_RECORDER_RELEASE_ZIP, dest)

    if latest:
        latest.artifact_filename = "feature-recorder-win64.zip"
        latest.artifact_stored_name = stored_name
        return dest.is_file()

    db.add(
        ToolVersion(
            tool_id=tool.id,
            version_label="1.0.0",
            manual_md=_RECORDER_MANUAL,
            changelog_md="",
            artifact_filename="feature-recorder-win64.zip",
            artifact_stored_name=stored_name,
            created_by_user_id=oid,
        )
    )
    return dest.is_file()


def _sync_recorder_artifact(db: Session, tool: Tool, owner_id: int) -> None:
    """启动时同步功能录制制品（若 release zip 已构建）。"""
    sync_feature_recorder_artifact(db, tool, owner_id=owner_id)


def ensure_tool_hub_startup(engine: Engine) -> None:
    """建表后确保内置工具存在。"""
    insp = inspect(engine)
    if not insp.has_table("tools"):
        return

    SessionLocal = sessionmaker(bind=engine)
    db: Session = SessionLocal()
    try:
        owner_id = _admin_user_id(db)

        _ensure_platform_tool(
            db,
            slug=_TRANSLATE_SLUG,
            display_name="AI 翻译",
            link_url="/translate",
            manual_md=_TRANSLATE_MANUAL,
            owner_id=owner_id,
        )

        recorder = _ensure_client_tool(
            db,
            slug=_RECORDER_SLUG,
            display_name="功能录制",
            manual_md=_RECORDER_MANUAL,
            owner_id=owner_id,
        )
        _sync_recorder_artifact(db, recorder, owner_id)

        db.commit()
    finally:
        db.close()
