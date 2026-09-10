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
# 底部白边裁剪：连续接近纯白的行占比超过此阈值才裁（0~255，越高越「必须是白」）
_WHITE_LUMA_MIN = 248
# 底部至少保留的像素，避免裁掉表格最后一丝边框
_CROP_KEEP_BOTTOM_PX = 4


def _crop_trailing_whitespace(png: bytes) -> bytes:
    """
    裁掉截图底部大片留白（flex/100vh 撑高时常见）。
    依赖 Pillow；失败则原样返回。
    """
    try:
        from io import BytesIO

        from PIL import Image
    except ImportError:
        return png
    try:
        img = Image.open(BytesIO(png)).convert("RGB")
    except Exception:  # noqa: BLE001
        return png
    w, h = img.size
    if h < 40 or w < 40:
        return png
    pixels = img.load()
    last_content_y = 0
    for y in range(h - 1, -1, -1):
        row_has_content = False
        # 抽样扫描，大图更快
        step = max(1, w // 400)
        for x in range(0, w, step):
            r, g, b = pixels[x, y]
            if r < _WHITE_LUMA_MIN or g < _WHITE_LUMA_MIN or b < _WHITE_LUMA_MIN:
                row_has_content = True
                break
        if row_has_content:
            last_content_y = y
            break
    new_h = min(h, last_content_y + 1 + _CROP_KEEP_BOTTOM_PX)
    # 裁掉不足 8% 高度时不改，避免无意义重编码
    if new_h >= h * 0.92:
        return png
    if new_h < 20:
        return png
    cropped = img.crop((0, 0, w, new_h))
    out = BytesIO()
    cropped.save(out, format="PNG", optimize=True)
    log.info("screenshot cropped whitespace %sx%s -> %sx%s", w, h, w, new_h)
    return out.getvalue()


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

                # 用 JS 强制贴合内容高度，解除 flex/100vh 拉伸（大片留白主因）
                try:
                    page.evaluate(
                        """() => {
                          document.documentElement.style.setProperty('height', 'auto', 'important');
                          document.documentElement.style.setProperty('min-height', '0', 'important');
                          document.documentElement.style.setProperty('overflow', 'visible', 'important');
                          document.body.style.setProperty('height', 'auto', 'important');
                          document.body.style.setProperty('min-height', '0', 'important');
                          document.body.style.setProperty('overflow', 'visible', 'important');

                          const selectors = [
                            '.tm-public-screen',
                            '.tm-screen',
                            '.tm-screen__body',
                            '.tm-screen__main',
                            '.tm-screen__side',
                            '.tm-screen__table-scroll',
                            '.tm-screen__detail-wrap',
                            '.tm-screen__content',
                            '.tm-screen__task-list',
                          ];
                          selectors.forEach(sel => {
                            document.querySelectorAll(sel).forEach(el => {
                              el.style.setProperty('display', 'block', 'important');
                              el.style.setProperty('height', 'auto', 'important');
                              el.style.setProperty('min-height', '0', 'important');
                              el.style.setProperty('max-height', 'none', 'important');
                              el.style.setProperty('overflow', 'visible', 'important');
                              el.style.setProperty('flex', 'none', 'important');
                            });
                          });
                          document.querySelectorAll('.tm-screen__table-scroll').forEach(el => {
                            el.style.setProperty('border', 'none', 'important');
                            el.style.setProperty('padding', '0', 'important');
                            el.style.setProperty('margin', '0', 'important');
                          });
                          document.querySelectorAll('.tm-screen__section-head').forEach(el => {
                            el.style.setProperty('display', 'none', 'important');
                          });
                          // 滚动容器高度锁死为内部 table 实际高度，避免 flex 子项仍占满视口
                          document.querySelectorAll('[data-testid="tm-screen-table"]').forEach(wrap => {
                            const table = wrap.querySelector('table');
                            if (!table) return;
                            const h = Math.ceil(table.getBoundingClientRect().height);
                            if (h > 0) {
                              wrap.style.setProperty('height', h + 'px', 'important');
                              wrap.style.setProperty('min-height', '0', 'important');
                            }
                          });
                          window.scrollTo(0, 0);
                          document.documentElement.offsetHeight;
                        }"""
                    )
                    page.wait_for_timeout(400)
                except Exception:  # noqa: BLE001
                    pass

                target_el = None
                clip_box = None
                if detail_only:
                    # 优先用 <table> 的真实包围盒做 clip，避免容器被 100vh/flex 撑高
                    clip_box = page.evaluate(
                        """() => {
                          const wrap = document.querySelector('[data-testid="tm-screen-table"]');
                          const table = wrap && wrap.querySelector('table');
                          const el = table || wrap || document.querySelector('[data-testid="tm-screen-detail"]');
                          if (!el) return null;
                          const r = el.getBoundingClientRect();
                          const x = Math.max(0, Math.floor(r.x));
                          const y = Math.max(0, Math.floor(r.y));
                          const width = Math.max(1, Math.ceil(r.width));
                          const height = Math.max(1, Math.ceil(r.height));
                          return { x, y, width, height };
                        }"""
                    )
                    target_el = (
                        page.query_selector(
                            f'[data-testid="{SCREEN_TABLE_TESTID}"] table'
                        )
                        or page.query_selector(
                            f'[data-testid="{SCREEN_TABLE_TESTID}"]'
                        )
                        or page.query_selector(
                            f'[data-testid="{SCREEN_DETAIL_TESTID}"]'
                        )
                    )
                if target_el is None:
                    target_el = page.query_selector(f'[data-testid="{SCREEN_ROOT_TESTID}"]')

                if clip_box and isinstance(clip_box, dict) and clip_box.get("height"):
                    # clip 相对视口；先滚到顶部保证坐标有效
                    page.evaluate("() => window.scrollTo(0, 0)")
                    page.wait_for_timeout(100)
                    # 若表格高于视口，临时拉高 viewport，再 clip（避免拼接错位留白）
                    need_h = int(clip_box["y"]) + int(clip_box["height"]) + 8
                    if need_h > vh:
                        page.set_viewport_size({"width": vw, "height": min(need_h, 16000)})
                        page.wait_for_timeout(150)
                        clip_box = page.evaluate(
                            """() => {
                              const wrap = document.querySelector('[data-testid="tm-screen-table"]');
                              const table = wrap && wrap.querySelector('table');
                              const el = table || wrap;
                              if (!el) return null;
                              const r = el.getBoundingClientRect();
                              return {
                                x: Math.max(0, Math.floor(r.x)),
                                y: Math.max(0, Math.floor(r.y)),
                                width: Math.max(1, Math.ceil(r.width)),
                                height: Math.max(1, Math.ceil(r.height)),
                              };
                            }"""
                        )
                    if clip_box:
                        png = page.screenshot(
                            type="png",
                            clip={
                                "x": float(clip_box["x"]),
                                "y": float(clip_box["y"]),
                                "width": float(clip_box["width"]),
                                "height": float(clip_box["height"]),
                            },
                        )
                    elif target_el is not None:
                        png = target_el.screenshot(type="png")
                    else:
                        png = page.screenshot(type="png", full_page=False)
                elif target_el is not None:
                    target_el.scroll_into_view_if_needed()
                    page.wait_for_timeout(150)
                    png = target_el.screenshot(type="png")
                else:
                    png = page.screenshot(type="png", full_page=False)
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

    png = _crop_trailing_whitespace(png)

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
