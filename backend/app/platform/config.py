"""
应用配置：从项目根目录 .env 加载，供 A/B 机分离部署。

.env 路径：<项目根>/ .env（与 backend/、frontend/ 同级）
"""

from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path

from dotenv import load_dotenv

# backend/app/platform/config.py → 项目根 = parents[3]
PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = PROJECT_ROOT / ".env"

load_dotenv(ENV_FILE)


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    return int(raw)


# ==================== 端口（A/B 机可分别配置） ====================

BACKEND_PORT = _int_env("BACKEND_PORT", 48010)
FRONTEND_PORT = _int_env("FRONTEND_PORT", 3003)

# ==================== LLM API Key ====================

MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY", "").strip()
MIMO_API_KEY = os.getenv("MIMO_API_KEY", "").strip()

MINIMAX_API_URL = os.getenv("MINIMAX_API_URL", "https://api.minimaxi.com/v1").strip()
MINIMAX_MODEL = os.getenv("MINIMAX_MODEL", "MiniMax-M2.7-highspeed").strip()

# ==================== Tavily（AI 早报搜索） ====================

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "").strip()
TAVILY_SEARCH_URL = os.getenv("TAVILY_SEARCH_URL", "https://api.tavily.com/search").strip()

_BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _resolve_data_path(env_name: str, default: Path) -> Path:
    """从环境变量读取目录路径；未设置则用 default。"""
    raw = os.getenv(env_name, "").strip()
    if raw:
        return Path(raw)
    return default


# ==================== Translate 磁盘目录 ====================

TRANSLATE_UPLOAD_DIR = _resolve_data_path(
    "TRANSLATE_UPLOAD_DIR",
    _BACKEND_ROOT / "app" / "uploads",
)
TRANSLATE_RESULT_DIR = _resolve_data_path(
    "TRANSLATE_RESULT_DIR",
    _BACKEND_ROOT / "app" / "results",
)

# ==================== AI 早报输出目录 ====================

AI_NEWS_OUTPUT_DIR = _resolve_data_path(
    "AI_NEWS_OUTPUT_DIR",
    PROJECT_ROOT / "data" / "ai_news",
)

# ==================== 认证 / 数据库 ====================

_SECRET_KEY = os.getenv("SECRET_KEY", "").strip()
if not _SECRET_KEY:
    if os.getenv("ENV", "dev") == "production":
        sys.exit("FATAL: SECRET_KEY must be set in production (.env or environment).")
    warnings.warn("SECRET_KEY not set, using insecure default — DO NOT use in production!")
    _SECRET_KEY = "dev-only-insecure-key"

SECRET_KEY = _SECRET_KEY
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./database.sqlite")

# ==================== 运行参数 ====================

MAX_CONCURRENT_JOBS = _int_env("MAX_CONCURRENT_JOBS", 1)
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")

if os.getenv("ENV", "dev") == "production" and not MINIMAX_API_KEY:
    sys.exit("FATAL: MINIMAX_API_KEY must be set in production (.env or environment).")
