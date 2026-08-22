"""
钉钉自定义机器人配图：内嵌 data-URI（不依赖公网图床 / 内网 URL）。

策略：只截 Task 明细后，按高度切成多条高清 JPEG（少缩宽、偏高质量），
每条仍控制在 webhook ~20KB 内。
"""
from __future__ import annotations

import base64
import logging
from io import BytesIO

log = logging.getLogger("app.test_manage.image_embed")

# 单条内嵌 JPEG 上限（base64≈*4/3 + 标题 < 20KB body）
DINGTALK_EMBED_JPEG_MAX_BYTES = 12_000
# 多切几片 → 每片更矮 → 可保留更宽、更高 JPEG 质量
DINGTALK_EMBED_MAX_SLICES = 8
DINGTALK_EMBED_MIN_SLICE_HEIGHT = 160
# 尽量保持的显示宽度（像素）；不够体积再降
DINGTALK_EMBED_PREFERRED_WIDTH = 1100


def png_to_jpeg_data_uri_slices(
    png_bytes: bytes,
    *,
    max_slices: int = DINGTALK_EMBED_MAX_SLICES,
    max_jpeg_bytes: int = DINGTALK_EMBED_JPEG_MAX_BYTES,
    preferred_width: int = DINGTALK_EMBED_PREFERRED_WIDTH,
) -> list[str]:
    """
    将明细截图切成若干较清晰的 JPEG data-URI。

    优先保宽保质量；体积不够时再增加切片数 / 略降质量，而不是一上来压糊。
    """
    raw = png_bytes or b""
    if not raw:
        return []
    try:
        from PIL import Image
    except ImportError:
        log.warning("Pillow missing; cannot embed screenshot")
        return []

    try:
        img = Image.open(BytesIO(raw)).convert("RGB")
    except Exception as exc:  # noqa: BLE001
        log.warning("open screenshot failed: %s", exc)
        return []

    # 仅当远大于目标宽时才缩小（2x 截图常见 2000+）
    if img.width > preferred_width * 1.35:
        ratio = preferred_width / float(img.width)
        img = img.resize(
            (preferred_width, max(1, int(img.height * ratio))),
            Image.Resampling.LANCZOS,
        )

    # 按高度估算需要几片：宁多勿糊
    n = max(1, min(int(max_slices), 10))
    # 经验：每片高度约 280~400px @1100w 时 JPEG q70 较易落在 12KB 内
    target_band = 320
    need = max(1, (img.height + target_band - 1) // target_band)
    n = max(n if n >= need else need, 1)
    n = min(n, 10)

    h = img.height
    slice_h = max(DINGTALK_EMBED_MIN_SLICE_HEIGHT, (h + n - 1) // n)
    while n > 1 and slice_h * (n - 1) >= h:
        n -= 1
        slice_h = max(DINGTALK_EMBED_MIN_SLICE_HEIGHT, (h + n - 1) // n)

    uris: list[str] = []
    y = 0
    idx = 0
    while y < h and idx < n:
        y2 = h if idx == n - 1 else min(h, y + slice_h)
        if idx == n - 1:
            y2 = h
        band = img.crop((0, y, img.width, y2))
        jpeg = _compress_band_hq(band, max_jpeg_bytes=max_jpeg_bytes)
        if jpeg:
            uris.append(
                "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")
            )
        y = y2
        idx += 1

    log.info(
        "screenshot embed slices=%s src=%sx%s bytes_in=%s",
        len(uris),
        img.width,
        img.height,
        len(raw),
    )
    return uris


def _compress_band_hq(img, *, max_jpeg_bytes: int) -> bytes | None:
    """
    高清晰优先：先试原宽 + 较高 quality；不够再略缩宽 / 降质。
    """
    from PIL import Image

    cur = img
    # 宽从大到小；质量从高到低
    widths = []
    for w in (cur.width, 1000, 900, 800, 700, 600):
        if w > 0 and w not in widths and w <= cur.width:
            widths.append(w)
    qualities = (82, 75, 68, 60, 52, 42, 32)

    best: bytes | None = None
    for w in widths:
        if cur.width != w:
            ratio = w / float(cur.width)
            scaled = cur.resize(
                (w, max(1, int(cur.height * ratio))), Image.Resampling.LANCZOS
            )
        else:
            scaled = cur
        for q in qualities:
            buf = BytesIO()
            scaled.save(buf, format="JPEG", quality=q, optimize=True, subsampling=0)
            data = buf.getvalue()
            if best is None or len(data) < len(best):
                best = data
            if len(data) <= max_jpeg_bytes:
                return data
    return best
