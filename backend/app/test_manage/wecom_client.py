"""
企业微信群机器人 webhook 客户端。

文档：https://developer.work.weixin.qq.com/document/path/91770
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

log = logging.getLogger("app.test_manage.wecom")

# 企微接口超时（秒）
WECOM_HTTP_TIMEOUT_SECONDS = 15
# 发送失败重试：次数与间隔（秒）—— 宁可多试，不能静默失败
WECOM_SEND_MAX_ATTEMPTS = 4
WECOM_SEND_RETRY_DELAY_SECONDS = 2.0


async def send_markdown(webhook_url: str, content: str) -> dict[str, Any]:
    """
    向群机器人发送【一条】markdown 消息（带重试）。

    成功时返回企微 JSON（errcode=0）；全部重试失败才抛 RuntimeError。
    调用方须保证 content UTF-8 长度 ≤ 企微单条上限（约 4096 字节）。
    """
    url = (webhook_url or "").strip()
    if not url:
        raise RuntimeError("未配置 WECOM_WEBHOOK_URL")

    nbytes = len((content or "").encode("utf-8"))
    if nbytes > 4096:
        raise RuntimeError(
            f"企微消息超长（{nbytes} bytes > 4096），拒绝发送；请缩短日报/周报内容"
        )

    payload = {"msgtype": "markdown", "markdown": {"content": content}}
    last_err: Exception | None = None

    for attempt in range(1, WECOM_SEND_MAX_ATTEMPTS + 1):
        try:
            async with httpx.AsyncClient(timeout=WECOM_HTTP_TIMEOUT_SECONDS) as client:
                resp = await client.post(url, json=payload)
                try:
                    data = resp.json()
                except Exception as exc:  # noqa: BLE001
                    raise RuntimeError(
                        f"企微 webhook 返回非 JSON：HTTP {resp.status_code}"
                    ) from exc

            errcode = data.get("errcode", -1)
            if resp.status_code >= 400 or errcode != 0:
                raise RuntimeError(
                    f"企微推送失败：HTTP {resp.status_code} errcode={errcode} "
                    f"errmsg={data.get('errmsg')}"
                )
            log.info(
                "wecom markdown sent, bytes≈%s attempt=%s", nbytes, attempt
            )
            return data
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            log.warning(
                "wecom send attempt %s/%s failed: %s",
                attempt,
                WECOM_SEND_MAX_ATTEMPTS,
                exc,
            )
            if attempt < WECOM_SEND_MAX_ATTEMPTS:
                await asyncio.sleep(WECOM_SEND_RETRY_DELAY_SECONDS)

    raise RuntimeError(f"企微推送彻底失败（已重试 {WECOM_SEND_MAX_ATTEMPTS} 次）: {last_err}")
