"""
Office 文档转换：.doc 等旧格式通过 LibreOffice 转为 docx 后解析。
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

# Windows 常见 LibreOffice 安装路径
_WINDOWS_SOFFICE_CANDIDATES = (
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
)


def find_soffice_executable() -> str | None:
    """查找 LibreOffice soffice 可执行文件。"""
    env_path = os.getenv("LIBREOFFICE_SOFFICE_PATH", "").strip()
    if env_path and Path(env_path).is_file():
        return env_path

    found = shutil.which("soffice")
    if found:
        return found

    for candidate in _WINDOWS_SOFFICE_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
    return None


def convert_with_libreoffice(source: Path, out_dir: Path, target_format: str) -> Path | None:
    """
    使用 LibreOffice 无头模式转换文档。

    :param source: 源文件
    :param out_dir: 输出目录
    :param target_format: 如 docx / pdf
    :return: 转换后的文件路径；失败返回 None
    """
    soffice = find_soffice_executable()
    if not soffice:
        return None

    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        soffice,
        "--headless",
        "--convert-to",
        target_format,
        "--outdir",
        str(out_dir),
        str(source),
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if result.returncode != 0:
            log.warning("LibreOffice 转换失败: %s", result.stderr or result.stdout)
            return None
    except (subprocess.TimeoutExpired, OSError) as exc:
        log.warning("LibreOffice 调用异常: %s", exc)
        return None

    converted = out_dir / f"{source.stem}.{target_format}"
    return converted if converted.is_file() else None
