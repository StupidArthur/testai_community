"""
阶段零：文档转换。

输入：.docx / .pdf / .md 文件
处理：统一转为 markdown 纯文本
输出：raw_text（原始 markdown 文本）

约束：
- .docx 使用 pandoc 转换（不使用 LLM）
- .pdf 使用 pdfplumber 提取文本
- .md 直接读取
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

# 支持的扩展名（小写）
SUPPORTED_EXTENSIONS = {".docx", ".pdf", ".md", ".markdown"}

# pandoc 可执行文件：优先环境变量，其次 PATH
PANDOC_ENV_KEY = "PANDOC_PATH"

# 子进程超时（秒）
PANDOC_TIMEOUT_SECONDS = 120


class ConverterError(RuntimeError):
    """文档转换失败。"""


def resolve_pandoc_executable() -> str:
    """
    解析 pandoc 可执行路径。

    顺序：环境变量 PANDOC_PATH → PATH 中的 pandoc。
    找不到则抛出 ConverterError，提示安装方式。
    """
    env_path = (os.environ.get(PANDOC_ENV_KEY) or "").strip()
    if env_path:
        candidate = Path(env_path)
        if candidate.is_file():
            return str(candidate.resolve())
        raise ConverterError(
            f"环境变量 {PANDOC_ENV_KEY}={env_path} 不是有效文件，请修正后重试。"
        )

    found = shutil.which("pandoc")
    if found:
        return found

    raise ConverterError(
        "未找到 pandoc。请安装后加入 PATH，或设置环境变量 "
        f"{PANDOC_ENV_KEY}=pandoc.exe 的完整路径。"
        " Windows 可用：winget install --id JohnMacFarlane.Pandoc"
    )


def convert_md_to_text(path: Path) -> str:
    """直接读取 Markdown 文件为文本（UTF-8）。"""
    return path.read_text(encoding="utf-8", errors="replace")


def convert_docx_to_markdown(path: Path, *, pandoc_bin: str | None = None) -> str:
    """
    使用 pandoc 将 .docx 转为 markdown 纯文本。

    参数：
        path: docx 文件路径
        pandoc_bin: 可选，指定 pandoc 可执行文件；默认自动解析
    """
    exe = pandoc_bin or resolve_pandoc_executable()
    cmd = [
        exe,
        str(path.resolve()),
        "-t",
        "markdown",
        "--wrap=none",
    ]
    log.info("pandoc convert: %s", path.name)
    try:
        completed = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=PANDOC_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise ConverterError(
            f"pandoc 转换超时（>{PANDOC_TIMEOUT_SECONDS}s）: {path.name}"
        ) from exc
    except OSError as exc:
        raise ConverterError(f"无法启动 pandoc: {exc}") from exc

    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "").strip()
        raise ConverterError(
            f"pandoc 转换失败（exit={completed.returncode}）: {path.name}; {err[:500]}"
        )

    return (completed.stdout or "").strip()


def convert_pdf_to_text(path: Path) -> str:
    """
    使用 pdfplumber 提取 PDF 文本，页与页之间以空行分隔，尽量贴近纯文本 markdown。
    """
    try:
        import pdfplumber
    except ImportError as exc:
        raise ConverterError(
            "未安装 pdfplumber，请执行: pip install pdfplumber"
        ) from exc

    pages: list[str] = []
    try:
        with pdfplumber.open(str(path.resolve())) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                page_text = page_text.strip()
                if page_text:
                    pages.append(page_text)
    except Exception as exc:  # noqa: BLE001 — 向调用方暴露可读错误
        raise ConverterError(f"pdfplumber 提取失败: {path.name}; {exc}") from exc

    return "\n\n".join(pages).strip()


def convert_document_to_raw_text(path: str | Path) -> str:
    """
    阶段零入口：将文档统一转为 raw_text（markdown / 纯文本）。

    参数：
        path: 本地文件路径（.docx / .pdf / .md）

    返回：
        raw_text 字符串；空文件返回空串。
    """
    file_path = Path(path)
    if not file_path.is_file():
        raise ConverterError(f"文件不存在: {file_path}")

    suffix = file_path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ConverterError(
            f"不支持的文件类型: {suffix}，仅支持 {sorted(SUPPORTED_EXTENSIONS)}"
        )

    if suffix in {".md", ".markdown"}:
        raw = convert_md_to_text(file_path)
    elif suffix == ".docx":
        raw = convert_docx_to_markdown(file_path)
    elif suffix == ".pdf":
        raw = convert_pdf_to_text(file_path)
    else:
        raise ConverterError(f"未处理的扩展名: {suffix}")

    log.info(
        "stage0 convert ok: file=%s bytes_in=%s chars_out=%s",
        file_path.name,
        file_path.stat().st_size,
        len(raw),
    )
    return raw


def main() -> None:
    """本地冒烟：修改下方路径后直接运行本文件。"""
    sample = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "sample.md"
    text = convert_document_to_raw_text(sample)
    print(f"[converter] file={sample.name} chars={len(text)}")
    print(text[:500])


if __name__ == "__main__":
    main()
