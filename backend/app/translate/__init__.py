"""FastAPI Web 服务：包装 record_translate，浏览器上传录制 zip → 翻译 → 下载结果。"""

from app.platform.config import TRANSLATE_RESULT_DIR, TRANSLATE_UPLOAD_DIR

__version__ = "0.1.0"

UPLOAD_DIR = TRANSLATE_UPLOAD_DIR
RESULT_DIR = TRANSLATE_RESULT_DIR

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
RESULT_DIR.mkdir(parents=True, exist_ok=True)
