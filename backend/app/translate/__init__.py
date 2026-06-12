"""FastAPI Web 服务：包装 record_translate，浏览器上传录制 zip → 翻译 → 下载结果。"""

from pathlib import Path

__version__ = "0.1.0"

BASE_DIR = Path(__file__).resolve().parent.parent.parent
UPLOAD_DIR = BASE_DIR / "app" / "uploads"
RESULT_DIR = BASE_DIR / "app" / "results"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
RESULT_DIR.mkdir(parents=True, exist_ok=True)
