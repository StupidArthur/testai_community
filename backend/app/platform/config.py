"""
应用配置：从项目根目录 .env 加载，供 A/B 机分离部署。

.env 路径：<项目根>/ .env（与 backend/、frontend/ 同级）
"""

from __future__ import annotations

import os
import shutil
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

# ==================== Ollama（本地 Embedding / 视觉） ====================

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").strip()
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "").strip()
OLLAMA_VL_MODEL = os.getenv("OLLAMA_VL_MODEL", "qwen2.5vl:7b").strip()
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "bge-m3").strip()
OLLAMA_VISION_PROMPT = os.getenv(
    "OLLAMA_VISION_PROMPT",
    "请详细描述这张图片中的文字、流程图结构、表格和关键信息，输出为可用于知识检索的纯文本。",
).strip()

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

# ==================== Tool Hub 制品目录 ====================

TOOL_HUB_ARTIFACT_DIR = _resolve_data_path(
    "TOOL_HUB_ARTIFACT_DIR",
    _BACKEND_ROOT / "app" / "tool_artifacts",
)
TOOL_HUB_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

# ==================== AI 早报输出目录 ====================

AI_NEWS_OUTPUT_DIR = _resolve_data_path(
    "AI_NEWS_OUTPUT_DIR",
    PROJECT_ROOT / "data" / "ai_news",
)

# ==================== 知识库（Knowledge Base） ====================

KNOWLEDGE_BASE_DATA_DIR = _resolve_data_path(
    "KNOWLEDGE_BASE_DATA_DIR",
    PROJECT_ROOT / "data" / "knowledge_base",
)
KNOWLEDGE_BASE_CHROMA_DIR = _resolve_data_path(
    "KNOWLEDGE_BASE_CHROMA_DIR",
    KNOWLEDGE_BASE_DATA_DIR / "chroma",
)
KNOWLEDGE_BASE_DATA_DIR.mkdir(parents=True, exist_ok=True)
KNOWLEDGE_BASE_CHROMA_DIR.mkdir(parents=True, exist_ok=True)

KB_MAX_UPLOAD_MB = _int_env("KB_MAX_UPLOAD_MB", 30)
KB_MAX_TOTAL_MB = _int_env("KB_MAX_TOTAL_MB", 500)
KB_MAX_DOCS_PER_KB = _int_env("KB_MAX_DOCS_PER_KB", 100)
KB_MAX_CONCURRENT_JOBS = _int_env("KB_MAX_CONCURRENT_JOBS", 2)
KB_CHUNK_SIZE = _int_env("KB_CHUNK_SIZE", 800)
KB_CHUNK_OVERLAP = _int_env("KB_CHUNK_OVERLAP", 120)
KB_RAG_TOP_K = _int_env("KB_RAG_TOP_K", 10)

# ==================== LibreOffice（.doc 转换） ====================

LIBREOFFICE_PROFILE_DIR = _resolve_data_path(
    "LIBREOFFICE_PROFILE_DIR",
    PROJECT_ROOT / "data" / "libreoffice_profile",
)
LIBREOFFICE_PROFILE_DIR.mkdir(parents=True, exist_ok=True)


def _resolve_libreoffice_soffice_path() -> str:
    """
    解析 soffice 可执行文件路径。

    优先级：环境变量 > 项目自带 tools/LibreOffice > PATH > Windows 默认安装目录。
    A/B 两套环境各自使用本目录 PROJECT_ROOT 下的 tools，互不干扰。
    """
    raw = os.getenv("LIBREOFFICE_SOFFICE_PATH", "").strip()
    if raw and Path(raw).is_file():
        return raw

    bundled_dir = PROJECT_ROOT / "tools" / "LibreOffice" / "program"
    bundled_candidates: list[Path] = []
    if os.name == "nt":
        bundled_candidates.append(bundled_dir / "soffice.com")
    bundled_candidates.append(bundled_dir / "soffice.exe")

    for candidate in bundled_candidates:
        if candidate.is_file():
            return str(candidate)

    found = shutil.which("soffice")
    if found:
        return found

    for candidate in (
        r"C:\Program Files\LibreOffice\program\soffice.com",
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.com",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    ):
        if Path(candidate).is_file():
            return candidate
    return ""


# 启动时解析一次；空字符串表示未找到
LIBREOFFICE_SOFFICE_PATH = _resolve_libreoffice_soffice_path()

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

# ==================== 钉钉群推送（测试任务日报/周报） ====================

DINGTALK_WEBHOOK_URL = os.getenv("DINGTALK_WEBHOOK_URL", "").strip()
# 自定义机器人安全关键词（须与钉钉后台一致）
DINGTALK_KEYWORD = os.getenv("DINGTALK_KEYWORD", "msg").strip() or "msg"
# 默认开启定时轮询；未配置 webhook 时定时任务会跳过实际发送
DINGTALK_PUSH_ENABLED = os.getenv("DINGTALK_PUSH_ENABLED", "true").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
# 幂等：同一 period 已成功发送则跳过（备份计划任务靠此避免重复发）
DINGTALK_PUSH_IDEMPOTENCY_ENABLED = os.getenv(
    "DINGTALK_PUSH_IDEMPOTENCY_ENABLED", "true"
).strip().lower() in ("1", "true", "yes", "on")
# 周报幂等单独开关（默认开：同周成功发送后跳过，避免 1 分钟轮询重复推群）
DINGTALK_WEEKLY_IDEMPOTENCY_ENABLED = os.getenv(
    "DINGTALK_WEEKLY_IDEMPOTENCY_ENABLED", "true"
).strip().lower() in ("1", "true", "yes", "on")


def _opt_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    return int(raw)


DINGTALK_DAILY_PUSH_HOUR = _opt_int_env("DINGTALK_DAILY_PUSH_HOUR", 20)
DINGTALK_DAILY_PUSH_MINUTE = _opt_int_env("DINGTALK_DAILY_PUSH_MINUTE", 0)
DINGTALK_WEEKLY_PUSH_WEEKDAY = _opt_int_env("DINGTALK_WEEKLY_PUSH_WEEKDAY", 2)  # Wed=2
DINGTALK_WEEKLY_PUSH_HOUR = _opt_int_env("DINGTALK_WEEKLY_PUSH_HOUR", 17)
DINGTALK_WEEKLY_PUSH_MINUTE = _opt_int_env("DINGTALK_WEEKLY_PUSH_MINUTE", 30)

# ==================== 运行参数 ====================

MAX_CONCURRENT_JOBS = _int_env("MAX_CONCURRENT_JOBS", 1)
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")

if os.getenv("ENV", "dev") == "production" and not MINIMAX_API_KEY:
    sys.exit("FATAL: MINIMAX_API_KEY must be set in production (.env or environment).")
