"""
钉钉群消息客户端。

通道：
1. 企业内部应用机器人 OpenAPI（优先）：高清截图走 media/upload + sampleImageMsg
2. 自定义机器人 Webhook（兜底）：关键词 msg；配图受约 20KB 限制

文档：
- Webhook https://open.dingtalk.com/document/orgapp/custom-bot-send-message-type
- OpenAPI https://open.dingtalk.com/document/orgapp/the-robot-sends-a-group-message
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import time
from typing import Any

import httpx

from app.platform.config import (
    DINGTALK_APP_KEY,
    DINGTALK_APP_SECRET,
    DINGTALK_KEYWORD,
    DINGTALK_OPEN_CONVERSATION_ID,
    DINGTALK_ROBOT_CODE,
    dingtalk_openapi_ready,
)

log = logging.getLogger("app.test_manage.dingtalk")

# 钉钉接口超时（秒）
DINGTALK_HTTP_TIMEOUT_SECONDS = 15
DINGTALK_MEDIA_UPLOAD_TIMEOUT_SECONDS = 60
# 发送失败重试
DINGTALK_SEND_MAX_ATTEMPTS = 4
DINGTALK_SEND_RETRY_DELAY_SECONDS = 2.0
# 钉钉 markdown 纯文字建议短；含 data-URI 配图时放宽到接近 webhook 20KB 上限
DINGTALK_MSG_MAX_BYTES = 4096
DINGTALK_MSG_MAX_BYTES_WITH_EMBED = 19_000
# OpenAPI 群消息正文相对宽松；仍控制在合理长度
DINGTALK_OPENAPI_MSG_MAX_BYTES = 12_000
# 自定义机器人整包 body 上限约 20KB（errcode 460101）；配图须压到此下
DINGTALK_WEBHOOK_BODY_MAX_BYTES = 20_000
# 压缩目标：预留 JSON/base64 开销后的原始图字节上限
DINGTALK_IMAGE_TARGET_RAW_BYTES = 12_000
# 兜底：未压缩前拒绝过大的异常截图
DINGTALK_IMAGE_MAX_BYTES = 1_800_000
# media/upload 图片上限 20MB；业务侧再收紧
DINGTALK_OPENAPI_IMAGE_MAX_BYTES = 18_000_000
# access_token 本地缓存（秒）；钉钉 token 有效约 7200s
DINGTALK_TOKEN_CACHE_TTL_SECONDS = 5400

_OPENAPI_TOKEN_CACHE: dict[str, Any] = {"token": "", "expire_at": 0.0}

DINGTALK_GETTOKEN_URL = "https://oapi.dingtalk.com/gettoken"
DINGTALK_MEDIA_UPLOAD_URL = "https://oapi.dingtalk.com/media/upload"
DINGTALK_GROUP_MESSAGES_SEND_URL = (
    "https://api.dingtalk.com/v1.0/robot/groupMessages/send"
)
# 官方图片模板字段名为 photoURL；实测可填 media/upload 返回的 media_id
DINGTALK_OPENAPI_IMAGE_MSG_KEY = "sampleImageMsg"
DINGTALK_OPENAPI_MARKDOWN_MSG_KEY = "sampleMarkdown"
DINGTALK_OPENAPI_ACTION_CARD_MSG_KEY = "sampleActionCard"
# 日报一条消息里的少量说明（无阻塞明细）
DINGTALK_DAILY_BRIEF_TEXT = "今日大屏 Action 明细见下图；完整交互请点详情链接打开大屏。"
DINGTALK_WEEKLY_BRIEF_TEXT = "本周大屏 Task 明细见下图；完整交互请点详情链接打开大屏。"
DINGTALK_DAILY_SCREENSHOT_FILENAME = "今日大屏明细.png"
DINGTALK_WEEKLY_SCREENSHOT_FILENAME = "本周大屏明细.png"


def _ensure_keyword(text: str, keyword: str) -> str:
    """钉钉自定义关键词：文本须包含关键词，否则机器人拒收。"""
    kw = (keyword or "").strip()
    if not kw:
        return text
    if kw in (text or ""):
        return text
    return f"{text} [{kw}]"


def _compress_image_for_webhook(
    raw: bytes, *, max_raw_bytes: int = DINGTALK_IMAGE_TARGET_RAW_BYTES
) -> bytes:
    """
    将截图压到钉钉自定义机器人可发送的体积（整包 < 20KB）。
    输出 JPEG；失败则返回原图（由上层校验）。
    """
    if not raw:
        return raw
    if len(raw) <= max_raw_bytes:
        return raw
    try:
        from io import BytesIO

        from PIL import Image
    except ImportError:
        log.warning("Pillow missing; cannot compress screenshot for webhook")
        return raw

    try:
        img = Image.open(BytesIO(raw)).convert("RGB")
    except Exception as exc:  # noqa: BLE001
        log.warning("open screenshot for compress failed: %s", exc)
        return raw

    widths = [960, 720, 560, 420, 320]
    qualities = [55, 40, 30, 22, 15]
    best = raw
    for w in widths:
        if img.width > w:
            ratio = w / float(img.width)
            resized = img.resize(
                (w, max(1, int(img.height * ratio))), Image.Resampling.LANCZOS
            )
        else:
            resized = img
        for q in qualities:
            buf = BytesIO()
            resized.save(buf, format="JPEG", quality=q, optimize=True)
            data = buf.getvalue()
            if len(data) < len(best):
                best = data
            if len(data) <= max_raw_bytes:
                log.info(
                    "compressed screenshot %s -> %s bytes (w=%s q=%s)",
                    len(raw),
                    len(data),
                    resized.width,
                    q,
                )
                return data
    log.warning(
        "screenshot still large after compress: %s -> %s (limit %s)",
        len(raw),
        len(best),
        max_raw_bytes,
    )
    return best


async def _post_webhook(webhook_url: str, payload: dict[str, Any]) -> dict[str, Any]:
    """带重试地 POST 钉钉 webhook。"""
    url = (webhook_url or "").strip()
    if not url:
        raise RuntimeError("未配置 DINGTALK_WEBHOOK_URL")

    last_err: Exception | None = None
    for attempt in range(1, DINGTALK_SEND_MAX_ATTEMPTS + 1):
        try:
            async with httpx.AsyncClient(timeout=DINGTALK_HTTP_TIMEOUT_SECONDS) as client:
                resp = await client.post(url, json=payload)
                try:
                    data = resp.json()
                except Exception as exc:  # noqa: BLE001
                    raise RuntimeError(
                        f"钉钉 webhook 返回非 JSON：HTTP {resp.status_code}"
                    ) from exc

            errcode = data.get("errcode", -1)
            if resp.status_code >= 400 or errcode != 0:
                raise RuntimeError(
                    f"钉钉推送失败：HTTP {resp.status_code} errcode={errcode} "
                    f"errmsg={data.get('errmsg')}"
                )
            log.info(
                "dingtalk post ok attempt=%s msgtype=%s",
                attempt,
                payload.get("msgtype"),
            )
            return data
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            log.warning(
                "dingtalk send attempt %s/%s failed: %s",
                attempt,
                DINGTALK_SEND_MAX_ATTEMPTS,
                exc,
            )
            if attempt < DINGTALK_SEND_MAX_ATTEMPTS:
                await asyncio.sleep(DINGTALK_SEND_RETRY_DELAY_SECONDS)

    raise RuntimeError(
        f"钉钉推送彻底失败（已重试 {DINGTALK_SEND_MAX_ATTEMPTS} 次）: {last_err}"
    )


async def send_markdown(
    webhook_url: str,
    content: str,
    *,
    title: str = "测试任务通知",
    keyword: str | None = None,
) -> dict[str, Any]:
    """
    向钉钉群机器人发送【一条】markdown 消息（带重试）。

    成功时返回 JSON（errcode=0）；全部重试失败才抛 RuntimeError。
    关键词优先写进 title，避免正文末尾露出「[msg]」。
    """
    url = (webhook_url or "").strip()
    if not url:
        raise RuntimeError("未配置 DINGTALK_WEBHOOK_URL")

    kw = DINGTALK_KEYWORD if keyword is None else keyword
    nbytes = len((content or "").encode("utf-8"))
    limit = (
        DINGTALK_MSG_MAX_BYTES_WITH_EMBED
        if "data:image/" in (content or "")
        else DINGTALK_MSG_MAX_BYTES
    )
    if nbytes > limit:
        raise RuntimeError(
            f"钉钉消息超长（{nbytes} bytes > {limit}），"
            "拒绝发送；请缩短日报/周报内容"
        )

    # 关键词只写入 title（通知栏），绝不追加到正文，避免聊天末尾出现「[msg]」
    safe_title = _ensure_keyword(title or "测试任务通知", kw)
    safe_text = content or ""
    payload = {
        "msgtype": "markdown",
        "markdown": {
            "title": safe_title,
            "text": safe_text,
        },
    }
    return await _post_webhook(url, payload)


async def send_image(
    webhook_url: str,
    png_bytes: bytes,
) -> dict[str, Any]:
    """
    发送钉钉 image 消息（base64 + md5）。

    用于日报「今日大屏」截图；自动压缩以适配自定义机器人 20KB body 上限。
    """
    raw = png_bytes or b""
    if not raw:
        raise RuntimeError("空图片，无法发送")
    if len(raw) > DINGTALK_IMAGE_MAX_BYTES:
        raise RuntimeError(
            f"截图过大（{len(raw)} bytes > {DINGTALK_IMAGE_MAX_BYTES}），跳过配图"
        )

    raw = _compress_image_for_webhook(raw)
    b64 = base64.b64encode(raw).decode("ascii")
    approx_body = len(b64) + 80
    if approx_body > DINGTALK_WEBHOOK_BODY_MAX_BYTES:
        raise RuntimeError(
            f"压缩后仍超 webhook 上限（约 {approx_body} > {DINGTALK_WEBHOOK_BODY_MAX_BYTES}）"
        )

    md5 = hashlib.md5(raw).hexdigest()
    payload = {
        "msgtype": "image",
        "image": {
            "base64": b64,
            "md5": md5,
        },
    }
    return await _post_webhook(webhook_url, payload)


# ---------- 企业内部应用机器人 OpenAPI ----------


async def get_openapi_access_token(
    *,
    app_key: str | None = None,
    app_secret: str | None = None,
    force_refresh: bool = False,
) -> str:
    """用 AppKey/Secret 换 access_token（带进程内缓存）。"""
    key = (app_key if app_key is not None else DINGTALK_APP_KEY).strip()
    secret = (app_secret if app_secret is not None else DINGTALK_APP_SECRET).strip()
    if not key or not secret:
        raise RuntimeError("未配置 DINGTALK_APP_KEY / DINGTALK_APP_SECRET")

    now = time.time()
    cached = str(_OPENAPI_TOKEN_CACHE.get("token") or "")
    expire_at = float(_OPENAPI_TOKEN_CACHE.get("expire_at") or 0.0)
    if not force_refresh and cached and now < expire_at:
        return cached

    async with httpx.AsyncClient(timeout=DINGTALK_HTTP_TIMEOUT_SECONDS) as client:
        resp = await client.get(
            DINGTALK_GETTOKEN_URL,
            params={"appkey": key, "appsecret": secret},
        )
        data = resp.json()
    if resp.status_code >= 400 or int(data.get("errcode", -1)) != 0:
        raise RuntimeError(
            f"钉钉 gettoken 失败：HTTP {resp.status_code} "
            f"errcode={data.get('errcode')} errmsg={data.get('errmsg')}"
        )
    token = str(data.get("access_token") or "").strip()
    if not token:
        raise RuntimeError("钉钉 gettoken 未返回 access_token")
    _OPENAPI_TOKEN_CACHE["token"] = token
    _OPENAPI_TOKEN_CACHE["expire_at"] = now + DINGTALK_TOKEN_CACHE_TTL_SECONDS
    return token


async def upload_image_media(
    image_bytes: bytes,
    *,
    filename: str = "screen.png",
    access_token: str | None = None,
) -> str:
    """
    上传图片到钉钉媒体库，返回 media_id。

    用于应用机器人 sampleImageMsg（photoURL 填 media_id）。
    """
    raw = image_bytes or b""
    if not raw:
        raise RuntimeError("空图片，无法上传")
    if len(raw) > DINGTALK_OPENAPI_IMAGE_MAX_BYTES:
        raise RuntimeError(
            f"截图过大（{len(raw)} > {DINGTALK_OPENAPI_IMAGE_MAX_BYTES}），无法上传"
        )

    token = access_token or await get_openapi_access_token()
    # 按扩展名设 content-type；png/jpeg 均可
    lower = (filename or "screen.png").lower()
    ctype = "image/jpeg" if lower.endswith((".jpg", ".jpeg")) else "image/png"
    files = {"media": (filename, raw, ctype)}
    async with httpx.AsyncClient(timeout=DINGTALK_MEDIA_UPLOAD_TIMEOUT_SECONDS) as client:
        resp = await client.post(
            DINGTALK_MEDIA_UPLOAD_URL,
            params={"access_token": token, "type": "image"},
            data={"type": "image"},
            files=files,
        )
        data = resp.json()
    if resp.status_code >= 400 or int(data.get("errcode", -1)) != 0:
        raise RuntimeError(
            f"钉钉 media/upload 失败：HTTP {resp.status_code} "
            f"errcode={data.get('errcode')} errmsg={data.get('errmsg')}"
        )
    media_id = str(data.get("media_id") or "").strip()
    if not media_id:
        raise RuntimeError("钉钉 media/upload 未返回 media_id")
    log.info("dingtalk media upload ok media_id=%s bytes=%s", media_id[:24], len(raw))
    return media_id


async def send_openapi_group_message(
    *,
    msg_key: str,
    msg_param: dict[str, Any],
    open_conversation_id: str | None = None,
    robot_code: str | None = None,
    access_token: str | None = None,
) -> dict[str, Any]:
    """调用 robot/groupMessages/send。"""
    if not dingtalk_openapi_ready() and not (
        open_conversation_id and robot_code and (access_token or DINGTALK_APP_SECRET)
    ):
        # 允许显式传参覆盖配置；否则要求完整 OpenAPI 配置
        if not (open_conversation_id and robot_code):
            raise RuntimeError("未配置钉钉应用机器人 OpenAPI（cid / robotCode）")

    cid = (open_conversation_id or DINGTALK_OPEN_CONVERSATION_ID).strip()
    code = (robot_code or DINGTALK_ROBOT_CODE).strip()
    if not cid or not code:
        raise RuntimeError("缺少 openConversationId 或 robotCode")

    token = access_token or await get_openapi_access_token()
    body = {
        "msgKey": msg_key,
        "msgParam": json.dumps(msg_param, ensure_ascii=False),
        "openConversationId": cid,
        "robotCode": code,
    }
    headers = {
        "x-acs-dingtalk-access-token": token,
        "Content-Type": "application/json",
    }

    last_err: Exception | None = None
    for attempt in range(1, DINGTALK_SEND_MAX_ATTEMPTS + 1):
        try:
            async with httpx.AsyncClient(timeout=DINGTALK_HTTP_TIMEOUT_SECONDS) as client:
                resp = await client.post(
                    DINGTALK_GROUP_MESSAGES_SEND_URL,
                    headers=headers,
                    json=body,
                )
                try:
                    data = resp.json()
                except Exception as exc:  # noqa: BLE001
                    raise RuntimeError(
                        f"钉钉 OpenAPI 返回非 JSON：HTTP {resp.status_code}"
                    ) from exc
            if resp.status_code >= 400:
                raise RuntimeError(
                    f"钉钉 OpenAPI 发群失败：HTTP {resp.status_code} body={data}"
                )
            log.info(
                "dingtalk openapi send ok attempt=%s msgKey=%s processQueryKey=%s",
                attempt,
                msg_key,
                data.get("processQueryKey"),
            )
            return data
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            log.warning(
                "dingtalk openapi attempt %s/%s failed: %s",
                attempt,
                DINGTALK_SEND_MAX_ATTEMPTS,
                exc,
            )
            if attempt < DINGTALK_SEND_MAX_ATTEMPTS:
                await asyncio.sleep(DINGTALK_SEND_RETRY_DELAY_SECONDS)
    raise RuntimeError(
        f"钉钉 OpenAPI 推送彻底失败（已重试 {DINGTALK_SEND_MAX_ATTEMPTS} 次）: {last_err}"
    )


async def send_openapi_markdown(
    content: str,
    *,
    title: str = "测试任务通知",
    keyword: str | None = None,
) -> dict[str, Any]:
    """应用机器人发送 markdown（sampleMarkdown）。"""
    kw = DINGTALK_KEYWORD if keyword is None else keyword
    nbytes = len((content or "").encode("utf-8"))
    if nbytes > DINGTALK_OPENAPI_MSG_MAX_BYTES:
        raise RuntimeError(
            f"钉钉 OpenAPI 消息超长（{nbytes} > {DINGTALK_OPENAPI_MSG_MAX_BYTES}）"
        )
    safe_title = _ensure_keyword(title or "测试任务通知", kw)
    return await send_openapi_group_message(
        msg_key=DINGTALK_OPENAPI_MARKDOWN_MSG_KEY,
        msg_param={"title": safe_title, "text": content or ""},
    )


async def send_openapi_image(
    image_bytes: bytes,
    *,
    filename: str = "今日大屏明细.png",
) -> dict[str, Any]:
    """
    上传截图并以 sampleImageMsg 发到群。

    photoURL 填 media_id（与此前试发成功路径一致）。
    """
    media_id = await upload_image_media(image_bytes, filename=filename)
    return await send_openapi_group_message(
        msg_key=DINGTALK_OPENAPI_IMAGE_MSG_KEY,
        msg_param={"photoURL": media_id},
    )


async def send_openapi_daily_one_message(
    *,
    title: str,
    detail_url: str,
    screenshot_png: bytes | None,
    brief: str = DINGTALK_DAILY_BRIEF_TEXT,
    keyword: str | None = None,
    image_filename: str = DINGTALK_DAILY_SCREENSHOT_FILENAME,
) -> dict[str, Any]:
    """
    日/周报只发【一条】markdown：少量说明 + 明细截图 + 详情链接（无底部按钮）。

    使用 sampleMarkdown，避免 ActionCard 底部按钮。
    """
    kw = DINGTALK_KEYWORD if keyword is None else keyword
    safe_title = _ensure_keyword(title or "测试任务日报", kw)
    url = (detail_url or "").strip()
    parts = [
        f"### {title or '测试任务日报'}",
        "",
        (brief or "").strip() or DINGTALK_DAILY_BRIEF_TEXT,
    ]
    if screenshot_png:
        media_id = await upload_image_media(
            screenshot_png, filename=image_filename or DINGTALK_DAILY_SCREENSHOT_FILENAME
        )
        parts.extend(["", f"![]({media_id})"])
    if url:
        parts.extend(
            [
                "",
                f"**详情大屏**：[点此打开]({url})",
                url,
            ]
        )
    text = "\n".join(parts)
    return await send_openapi_group_message(
        msg_key=DINGTALK_OPENAPI_MARKDOWN_MSG_KEY,
        msg_param={"title": safe_title, "text": text},
    )


async def send_daily_report_messages(
    *,
    title: str,
    detail_url: str,
    screenshot_png: bytes | None,
    webhook_url: str | None = None,
    brief: str = DINGTALK_DAILY_BRIEF_TEXT,
    image_filename: str = DINGTALK_DAILY_SCREENSHOT_FILENAME,
) -> dict[str, Any]:
    """
    日/周报发送：【一条】少量说明 + 链接 + 截图。

    优先 OpenAPI；未配置则回退 Webhook 单条 markdown。
    """
    result: dict[str, Any] = {
        "channel": "",
        "ok": False,
        "image_ok": bool(screenshot_png),
    }
    if dingtalk_openapi_ready():
        result["channel"] = "openapi"
        await send_openapi_daily_one_message(
            title=title,
            detail_url=detail_url,
            screenshot_png=screenshot_png,
            brief=brief,
            image_filename=image_filename,
        )
        result["ok"] = True
        return result

    url = (webhook_url or "").strip()
    if not url:
        raise RuntimeError("未配置钉钉 OpenAPI 或 DINGTALK_WEBHOOK_URL")
    result["channel"] = "webhook"
    # Webhook：短文 + 链接；截图尽量压进同条 markdown（体积不够则仅文字链接）
    from app.test_manage.push_report import build_daily_brief_markdown

    md = build_daily_brief_markdown(
        title=title,
        detail_url=detail_url,
        brief=brief,
        image_data_uri=None,
    )
    if screenshot_png:
        try:
            # 复用 webhook 压缩后以 data-URI 塞进同条（可能失败则只发文字）
            raw = _compress_image_for_webhook(screenshot_png)
            b64 = base64.b64encode(raw).decode("ascii")
            uri = f"data:image/jpeg;base64,{b64}"
            md_with_img = build_daily_brief_markdown(
                title=title,
                detail_url=detail_url,
                brief=brief,
                image_data_uri=uri,
            )
            if len(md_with_img.encode("utf-8")) <= DINGTALK_MSG_MAX_BYTES_WITH_EMBED:
                md = md_with_img
            else:
                result["image_ok"] = False
        except Exception as exc:  # noqa: BLE001
            log.warning("webhook embed screenshot failed: %s", exc)
            result["image_ok"] = False
    await send_markdown(url, md, title=title)
    result["ok"] = True
    return result
