"""
钉钉自定义机器人群消息客户端。

安全设置需开启「自定义关键词」，默认关键词 msg（与 DINGTALK_KEYWORD 一致）。
文档：https://open.dingtalk.com/document/orgapp/custom-bot-send-message-type
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.platform.config import DINGTALK_KEYWORD

log = logging.getLogger("app.test_manage.dingtalk")

# 钉钉接口超时（秒）
DINGTALK_HTTP_TIMEOUT_SECONDS = 15
# 发送失败重试
DINGTALK_SEND_MAX_ATTEMPTS = 4
DINGTALK_SEND_RETRY_DELAY_SECONDS = 2.0
# 钉钉 markdown 正文偏宽松；仍按单条压缩口径控制（与组装层一致）
DINGTALK_MSG_MAX_BYTES = 4096


def _ensure_keyword(text: str, keyword: str) -> str:
    """钉钉自定义关键词：标题/正文须包含关键词，否则机器人拒收。"""
    kw = (keyword or "").strip()
    if not kw:
        return text
    if kw in (text or ""):
        return text
    return f"{text} [{kw}]"


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
    """
    url = (webhook_url or "").strip()
    if not url:
        raise RuntimeError("未配置 DINGTALK_WEBHOOK_URL")

    kw = DINGTALK_KEYWORD if keyword is None else keyword
    nbytes = len((content or "").encode("utf-8"))
    if nbytes > DINGTALK_MSG_MAX_BYTES:
        raise RuntimeError(
            f"钉钉消息超长（{nbytes} bytes > {DINGTALK_MSG_MAX_BYTES}），"
            "拒绝发送；请缩短日报/周报内容"
        )

    safe_title = _ensure_keyword(title or "测试任务通知", kw)
    safe_text = _ensure_keyword(content or "", kw)
    payload = {
        "msgtype": "markdown",
        "markdown": {
            "title": safe_title,
            "text": safe_text,
        },
    }
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
                "dingtalk markdown sent, bytes≈%s attempt=%s", nbytes, attempt
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
