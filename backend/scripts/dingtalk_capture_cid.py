"""
本机 Stream 收一次「老丁」被 @ 的消息，打印 openConversationId（conversationId）。

前提：
1. 开放平台该应用机器人消息接收模式 = Stream
2. 本机已能连公网
3. 重要：同一机器人通常只能有一条有效 Stream。
   若群里 @老丁 已有自动回复（如 pong），说明别人的服务已占用 Stream，
   需先停掉对方服务，或让对方在现有回调里打印 conversationId。

用法（backend 目录，改下面常量，无命令行参数）：
  python scripts/dingtalk_capture_cid.py

然后到群「我是一个群」里发：@老丁 ping
看到控制台打印 cid 后 Ctrl+C 结束。
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

try:
    from dotenv import load_dotenv

    load_dotenv(BACKEND_DIR.parent / ".env")
    load_dotenv(BACKEND_DIR / ".env")
except Exception:
    pass

# ========== 可改参数（优先读环境变量）==========
import os

CLIENT_ID = (os.getenv("DINGTALK_APP_KEY") or "dingjvvesrkwup6d8gix").strip()
CLIENT_SECRET = (os.getenv("DINGTALK_APP_SECRET") or "").strip()
# =============================================


def main() -> None:
    if not CLIENT_SECRET:
        raise SystemExit(
            "请先设置环境变量 DINGTALK_APP_SECRET，或在本文件 CLIENT_SECRET 填入 Secret"
        )

    import dingtalk_stream
    from dingtalk_stream import AckMessage

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    log = logging.getLogger("capture_cid")

    class CaptureHandler(dingtalk_stream.ChatbotHandler):
        async def process(self, callback: dingtalk_stream.CallbackMessage):
            data = callback.data
            if isinstance(data, str):
                data = json.loads(data)

            # 钉钉回调里 conversationId 即发群 OpenAPI 用的 openConversationId
            cid = (
                data.get("openConversationId")
                or data.get("conversationId")
                or data.get("chatId")
                or ""
            )
            title = data.get("conversationTitle") or ""
            text = ""
            if isinstance(data.get("text"), dict):
                text = (data["text"].get("content") or "").strip()

            print("\n========== 收到消息 ==========", flush=True)
            print(f"群名称 conversationTitle = {title}", flush=True)
            print(f"openConversationId      = {cid}", flush=True)
            print(f"文本                    = {text}", flush=True)
            print("完整回调 JSON：", flush=True)
            print(json.dumps(data, ensure_ascii=False, indent=2), flush=True)
            print("==============================\n", flush=True)

            try:
                incoming = dingtalk_stream.ChatbotMessage.from_dict(data)
                self.reply_text(
                    f"已捕获 openConversationId：\n{cid or '(空)'}",
                    incoming,
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("reply failed: %s", exc)

            return AckMessage.STATUS_OK, "OK"

    credential = dingtalk_stream.Credential(CLIENT_ID, CLIENT_SECRET)
    client = dingtalk_stream.DingTalkStreamClient(credential)
    client.register_callback_handler(
        dingtalk_stream.chatbot.ChatbotMessage.TOPIC,
        CaptureHandler(),
    )
    print(
        "Stream 已启动。请到群里发送：@老丁 ping\n"
        "若仍是别人的 pong、本脚本无输出，说明 Stream 被其它服务占用，需先停掉对方。\n"
        "结束：Ctrl+C\n",
        flush=True,
    )
    client.start_forever()


if __name__ == "__main__":
    main()
