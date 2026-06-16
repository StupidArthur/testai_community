"""
tool_hub 模块：工具集管理（客户端可下载工具 + 平台集成工具）。

磁盘目录由 platform.config.TOOL_HUB_ARTIFACT_DIR 配置。
"""

from __future__ import annotations

# 预留工具子类型，当前默认
DEFAULT_TOOL_TYPE = "default"

# 客户端工具包大小上限（字节）
MAX_ARTIFACT_BYTES = 200 * 1024 * 1024

# 允许的客户端工具扩展名
ALLOWED_CLIENT_EXTENSIONS = {".exe", ".zip", ".msi"}

# 列表默认分页
DEFAULT_PAGE_SIZE = 50
