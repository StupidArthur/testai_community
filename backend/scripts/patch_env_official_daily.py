# -*- coding: utf-8 -*-
"""62 生产机一键切换：日报目标群改为正式群 + 双项目模式（配套 部署日报到正式群.cmd）。

修改项目根 .env：
  DINGTALK_OPEN_CONVERSATION_ID=cidzwC6RW+70Wf6JXZItetliw==   # 正式群「TPT现场版本管理」
  DINGTALK_DAILY_PROJECT_IDS=65ddacfd-...                    # tpt2现场运维,TPT v2.3 产品包

幂等：重复运行结果一致；修改前自动备份 .env.bak_<时间戳>。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = PROJECT_ROOT / ".env"

# 正式群「TPT现场版本管理」（openConversationId，2026-09-09 经钉钉服务端搜索确认）
OFFICIAL_CID = "cidzwC6RW+70Wf6JXZItetliw=="
# 日报双项目：tpt2现场运维 + TPT v2.3 产品包
PROJECT_IDS = "65ddacfd-a223-4803-b628-fdc2df985832,ad490f62-cc57-49c5-854c-f078ed9ad5bd"
# 周报双项目：TPT v2.3 产品包在前 + tpt2现场运维在后（用户指定顺序）
WEEKLY_PROJECT_IDS = "ad490f62-cc57-49c5-854c-f078ed9ad5bd,65ddacfd-a223-4803-b628-fdc2df985832"

TARGETS = {
    "DINGTALK_OPEN_CONVERSATION_ID": OFFICIAL_CID,
    "DINGTALK_DAILY_PROJECT_IDS": PROJECT_IDS,
    "DINGTALK_WEEKLY_PROJECT_IDS": WEEKLY_PROJECT_IDS,
    # 关闭后端内置定时推送：改由 62 定时平台（tm_daily_push/tm_weekly_push）触发，
    # 避免两条链路重复发送（内置是 force 强发，不走"本日已推送"幂等）
    "DINGTALK_PUSH_ENABLED": "false",
}


def main() -> int:
    if not ENV_PATH.exists():
        print(f"[ERROR] 找不到 {ENV_PATH}")
        return 1
    raw = ENV_PATH.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    body = raw[3:] if bom else raw
    try:
        text = body.decode("utf-8")
        encoding = "utf-8"
    except UnicodeDecodeError:
        text = body.decode("gbk")
        encoding = "gbk"

    eol = "\r\n" if "\r\n" in text else "\n"
    ends_with_newline = text.endswith(("\n", "\r"))
    lines = text.splitlines()
    changed: dict[str, str] = {}
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line else ""
        if key in TARGETS:
            new_line = f"{key}={TARGETS[key]}"
            if line != new_line:
                changed[key] = f"{line} -> {new_line}"
            out.append(new_line)
            seen.add(key)
        else:
            out.append(line)
    for key, value in TARGETS.items():
        if key not in seen:
            out.append(f"{key}={value}")
            changed[key] = f"(新增) {key}={value}"

    new_text = eol.join(out) + (eol if ends_with_newline else "")
    new_raw = (b"\xef\xbb\xbf" if bom else b"") + new_text.encode(encoding)
    if new_raw != raw:
        stamp = time.strftime("%Y%m%d_%H%M%S")
        backup = ENV_PATH.with_name(f".env.bak_{stamp}")
        backup.write_bytes(raw)
        ENV_PATH.write_bytes(new_raw)
        print(f"[OK] 已备份到 {backup.name} 并写入修改：")
    else:
        print("[OK] .env 已是目标状态，无需修改：")
    for key in TARGETS:
        print(f"     {key}={TARGETS[key]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
