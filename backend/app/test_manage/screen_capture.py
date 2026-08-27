"""
公开大屏截图（Playwright），供钉钉日/周报配图。

默认只截明细区（不含 KPI / 筛选 / 标题栏），并提高 deviceScaleFactor。
依赖可选：未安装 playwright / 浏览器时返回 None，推送仍发详情链接。
入口仅函数参数，不使用命令行。
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from app.test_manage.config import (
    DINGTALK_DAILY_SCREENSHOT_ENABLED,
    DINGTALK_SCREENSHOT_TIMEOUT_MS,
    DINGTALK_SCREENSHOT_VIEWPORT_HEIGHT,
    DINGTALK_SCREENSHOT_VIEWPORT_WIDTH,
    resolve_public_today_screen_url,
    resolve_public_week_screen_url,
)

log = logging.getLogger("app.test_manage.screen_capture")

# 与前端 data-testid 对齐：优先只截明细，避免整屏
SCREEN_DETAIL_TESTID = "tm-screen-detail"
SCREEN_TABLE_TESTID = "tm-screen-table"
SCREEN_ROOT_TESTID = "tm-screen"
# 页面就绪：有明细表即可
READY_SELECTOR = (
    f'[data-testid="{SCREEN_TABLE_TESTID}"], '
    f'[data-testid="{SCREEN_DETAIL_TESTID}"], '
    f'[data-testid="{SCREEN_ROOT_TESTID}"]'
)
# 本周截图：展开后应出现 Action 行（无 Action 的空周则跳过）
WEEK_EXPANDED_SELECTOR = '[data-testid="tm-screen-action-row"]'
# 截图清晰度（2x 视网膜）
SCREENSHOT_DEVICE_SCALE = 2


def _ensure_windows_subprocess_loop() -> None:
    """
    Windows 下 uvicorn 使用 SelectorEventLoop（不支持子进程），
    Playwright 启动 Node 驱动会抛 NotImplementedError。
    在截图线程内把策略切回 Proactor；只影响之后新建的 loop，
    不影响已在运行的 uvicorn 主循环（其 loop 启动时已创建）。
    """
    if sys.platform == "win32":
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass


def capture_public_screen_png(
    *,
    url: str,
    timeout_ms: int | None = None,
    viewport_width: int | None = None,
    viewport_height: int | None = None,
    out_path: str | Path | None = None,
    detail_only: bool = True,
    label: str = "screen",
    wait_expanded: bool = False,
) -> bytes | None:
    """
    打开给定公开大屏 URL 并截取 PNG bytes。

    detail_only=True（默认）：只截明细区块。
    失败返回 None，由调用方决定是否仅发文字链接。
    """
    if not DINGTALK_DAILY_SCREENSHOT_ENABLED:
        log.info("screenshot disabled (DINGTALK_DAILY_SCREENSHOT_ENABLED=false)")
        return None

    _ensure_windows_subprocess_loop()

    target = (url or "").strip()
    if not target:
        log.warning("capture_public_screen_png: empty url")
        return None

    to = int(timeout_ms if timeout_ms is not None else DINGTALK_SCREENSHOT_TIMEOUT_MS)
    vw = int(viewport_width if viewport_width is not None else DINGTALK_SCREENSHOT_VIEWPORT_WIDTH)
    vh = int(
        viewport_height if viewport_height is not None else DINGTALK_SCREENSHOT_VIEWPORT_HEIGHT
    )

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.warning("playwright not installed; skip %s screenshot", label)
        return None

    png: bytes | None = None
    try:
        with sync_playwright() as p:
            browser = None
            launch_errors: list[str] = []
            for launch_kwargs in (
                {"handle_sigint": False, "handle_sigterm": False, "handle_sighup": False},
                {"channel": "msedge", "handle_sigint": False, "handle_sigterm": False, "handle_sighup": False},
                {"channel": "chrome", "handle_sigint": False, "handle_sigterm": False, "handle_sighup": False},
            ):
                try:
                    browser = p.chromium.launch(headless=True, **launch_kwargs)
                    if launch_kwargs:
                        log.info("screenshot browser fallback %s", launch_kwargs)
                    break
                except Exception as launch_exc:  # noqa: BLE001
                    launch_errors.append(f"{launch_kwargs or 'chromium'}: {launch_exc}")
                    browser = None
            if browser is None:
                raise RuntimeError("; ".join(launch_errors) or "no browser")
            try:
                page = browser.new_page(
                    viewport={"width": vw, "height": vh},
                    device_scale_factor=SCREENSHOT_DEVICE_SCALE,
                )
                page.goto(target, wait_until="networkidle", timeout=to)
                page.wait_for_selector(READY_SELECTOR, timeout=to)
                # 再等展开动画 / 截图模式自动展开 Task
                page.wait_for_timeout(1000)
                if wait_expanded:
                    try:
                        page.wait_for_selector(WEEK_EXPANDED_SELECTOR, timeout=min(8000, to))
                    except Exception:  # noqa: BLE001
                        # 空周或筛选无 Action：仍截 Task 表
                        log.info("%s screenshot: no expanded action rows", label)
                    page.wait_for_timeout(400)

                target_el = None
                if detail_only:
                    target_el = page.query_selector(
                        f'[data-testid="{SCREEN_DETAIL_TESTID}"]'
                    ) or page.query_selector(f'[data-testid="{SCREEN_TABLE_TESTID}"]')
                if target_el is None:
                    target_el = page.query_selector(f'[data-testid="{SCREEN_ROOT_TESTID}"]')

                if target_el is not None:
                    # 滚入视口，避免被裁切
                    target_el.scroll_into_view_if_needed()
                    page.wait_for_timeout(200)
                    png = target_el.screenshot(type="png")
                else:
                    png = page.screenshot(type="png", full_page=True)
            finally:
                browser.close()
    except Exception as exc:  # noqa: BLE001
        import traceback
        log.warning(
            "capture_public_screen_png failed label=%s url=%s err_type=%s err=%s\n%s",
            label,
            target,
            type(exc).__name__,
            exc,
            traceback.format_exc(),
        )
        return None

    if not png:
        return None

    if out_path is not None:
        path = Path(out_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(png)
        log.info("wrote screenshot %s (%s bytes)", path, len(png))

    log.info(
        "%s screenshot ok bytes=%s detail_only=%s url=%s",
        label,
        len(png),
        detail_only,
        target,
    )
    return png


def capture_public_screen_png_isolated(
    *,
    url: str,
    timeout_ms: int | None = None,
    out_path: str | Path | None = None,
    detail_only: bool = True,
    label: str = "screen",
    wait_expanded: bool = False,
) -> bytes | None:
    """
    子进程隔离截图（服务端调用入口）。

    原因：Windows 下在 uvicorn worker 内直接跑 Playwright 有两个坑——
    1) uvicorn 的 SelectorEventLoop 不支持子进程（NotImplementedError）；
    2) Chromium 启动/退出会向同控制台广播 CTRL_C，直接杀掉 worker 和同终端进程。
    子进程用 CREATE_NO_WINDOW 拥有独立（不可见）控制台，事件不再传播；
    PNG 经临时文件回传。
    """
    import subprocess
    import tempfile

    target = (url or "").strip()
    if not target:
        log.warning("capture_public_screen_png_isolated: empty url")
        return None

    to = int(timeout_ms if timeout_ms is not None else DINGTALK_SCREENSHOT_TIMEOUT_MS)
    backend_dir = Path(__file__).resolve().parents[2]

    child_code = (
        "import sys\n"
        "from app.test_manage.screen_capture import capture_public_screen_png\n"
        "png = capture_public_screen_png(\n"
        "    url=sys.argv[1], out_path=sys.argv[2], label=sys.argv[3],\n"
        "    wait_expanded=(sys.argv[4] == '1'), detail_only=(sys.argv[5] == '1'),\n"
        ")\n"
        "sys.exit(0 if png else 3)\n"
    )

    tmp = tempfile.NamedTemporaryFile(suffix=".png", prefix="tm_shot_", delete=False)
    tmp.close()
    try:
        cmd = [
            sys.executable,
            "-c",
            child_code,
            target,
            tmp.name,
            label,
            "1" if wait_expanded else "0",
            "1" if detail_only else "0",
        ]
        run_kwargs: dict = {
            "cwd": str(backend_dir),
            "capture_output": True,
            "timeout": to + 20,
        }
        if sys.platform == "win32":
            # CREATE_NO_WINDOW(0x08000000) | CREATE_NEW_PROCESS_GROUP(0x200)
            run_kwargs["creationflags"] = 0x08000000 | 0x00000200
        try:
            proc = subprocess.run(cmd, **run_kwargs)  # type: ignore[arg-type]
        except subprocess.TimeoutExpired:
            log.warning("isolated %s screenshot timeout url=%s", label, target)
            return None

        data = b""
        tmp_path = Path(tmp.name)
        if tmp_path.exists():
            data = tmp_path.read_bytes()

        if proc.returncode == 0 and data:
            log.info("%s screenshot(isolated) ok bytes=%s url=%s", label, len(data), target)
            if out_path is not None:
                p = Path(out_path)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(data)
            return data

        err_tail = (proc.stderr or b"")[-400:].decode("utf-8", "replace")
        log.warning(
            "isolated %s screenshot failed rc=%s url=%s stderr_tail=%s",
            label,
            proc.returncode,
            target,
            err_tail,
        )
        return None
    finally:
        Path(tmp.name).unlink(missing_ok=True)


def capture_today_screen_png(
    *,
    project_id: str | None = None,
    url: str | None = None,
    timeout_ms: int | None = None,
    viewport_width: int | None = None,
    viewport_height: int | None = None,
    out_path: str | Path | None = None,
    detail_only: bool = True,
) -> bytes | None:
    """打开公开今日大屏并截取 PNG bytes（子进程隔离，服务端安全）。"""
    target = (url or "").strip() or resolve_public_today_screen_url(
        project_id=project_id, screenshot=True
    )
    return capture_public_screen_png_isolated(
        url=target,
        timeout_ms=timeout_ms,
        out_path=out_path,
        detail_only=detail_only,
        label="daily",
    )


def capture_week_screen_png(
    *,
    project_id: str | None = None,
    url: str | None = None,
    timeout_ms: int | None = None,
    viewport_width: int | None = None,
    viewport_height: int | None = None,
    out_path: str | Path | None = None,
    detail_only: bool = True,
) -> bytes | None:
    """打开公开本周大屏（view=current）并截取 PNG bytes（子进程隔离，服务端安全）。"""
    target = (url or "").strip() or resolve_public_week_screen_url(
        project_id=project_id, screenshot=True
    )
    return capture_public_screen_png_isolated(
        url=target,
        timeout_ms=timeout_ms,
        out_path=out_path,
        detail_only=detail_only,
        label="weekly",
        wait_expanded=False,
    )


if __name__ == "__main__":
    data = capture_week_screen_png(
        project_id=None,
        url="http://127.0.0.1:3003/tm-screen?view=current&screenshot=1",
        out_path=Path(__file__).resolve().parents[2] / "_tmp_week_screen.png",
    )
    print("ok" if data else "failed", len(data or b""))
