"""
Office 文档转换：.doc 等旧格式通过 LibreOffice 转为 docx 后解析。
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from app.platform.config import LIBREOFFICE_PROFILE_DIR, LIBREOFFICE_SOFFICE_PATH

log = logging.getLogger(__name__)

_VC_REDIST_HINT = (
    "若已配置路径仍失败，请在本机运行一次 scripts/ensure_libreoffice.ps1 "
    "（安装 VC++ 运行库并校验 LibreOffice）。"
)


def find_soffice_executable() -> str | None:
    """查找 LibreOffice soffice 可执行文件。"""
    path = (LIBREOFFICE_SOFFICE_PATH or "").strip()
    if path and Path(path).is_file():
        return path
    return None


def _user_installation_arg() -> str:
    """LibreOffice 用户配置目录，避免无头模式写系统目录失败。"""
    profile_dir = LIBREOFFICE_PROFILE_DIR.resolve()
    profile_dir.mkdir(parents=True, exist_ok=True)
    return f"-env:UserInstallation={profile_dir.as_uri()}"


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
        log.warning("未找到 LibreOffice：请设置 LIBREOFFICE_SOFFICE_PATH 或安装 LibreOffice")
        return None

    out_dir.mkdir(parents=True, exist_ok=True)
    soffice_path = Path(soffice)
    cmd = [
        soffice,
        "--headless",
        _user_installation_arg(),
        "--convert-to",
        target_format,
        "--outdir",
        str(out_dir.resolve()),
        str(source.resolve()),
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
            cwd=str(soffice_path.parent),
        )
        if result.returncode != 0:
            log.warning(
                "LibreOffice 转换失败 (rc=%s) soffice=%s stderr=%s stdout=%s",
                result.returncode,
                soffice,
                result.stderr or "",
                result.stdout or "",
            )
            return None
    except (subprocess.TimeoutExpired, OSError) as exc:
        log.warning("LibreOffice 调用异常 soffice=%s: %s", soffice, exc)
        return None

    converted = out_dir / f"{source.stem}.{target_format}"
    return converted if converted.is_file() else None


def libreoffice_unavailable_message() -> str:
    """生成 .doc 解析失败时的用户提示。"""
    soffice = find_soffice_executable()
    if soffice:
        return (
            "无法解析 .doc 文件：LibreOffice 已找到但转换失败。"
            f"当前路径：{soffice}。"
            f"{_VC_REDIST_HINT}"
            "也可将文件另存为 .docx 后重新上传。"
        )
    return (
        "无法解析 .doc 文件。请安装 LibreOffice，或将文件另存为 .docx。"
        "也可设置环境变量 LIBREOFFICE_SOFFICE_PATH 指向 soffice.exe。"
        f"{_VC_REDIST_HINT}"
    )
