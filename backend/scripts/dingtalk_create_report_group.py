"""
新建一个钉钉企业内部群，并打印 openConversationId（无需 @ 机器人）。

适用：旧群 cid 无人知道、又不想 @ 抢 Stream。
新建群后把人拉进去，日报发到这个新群即可。

用法（backend 目录）：
  1. 设置环境变量 DINGTALK_APP_KEY / DINGTALK_APP_SECRET
  2. 设置你的手机号 DINGTALK_OWNER_MOBILE（用来查 userid 当群主）
  3. python scripts/dingtalk_create_report_group.py

也可在本文件顶部改常量。无命令行参数。
"""
from __future__ import annotations

import os
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

import httpx

# ========== 可改 ==========
APP_KEY = (os.getenv("DINGTALK_APP_KEY") or "dingjvvesrkwup6d8gix").strip()
APP_SECRET = (os.getenv("DINGTALK_APP_SECRET") or "").strip()
# 群主手机号（钉钉绑定的），用来换 userid
OWNER_MOBILE = (os.getenv("DINGTALK_OWNER_MOBILE") or "").strip()
# 额外成员 userid，逗号分隔，可空
MEMBER_USER_IDS = (os.getenv("DINGTALK_MEMBER_USER_IDS") or "").strip()
GROUP_NAME = (os.getenv("DINGTALK_NEW_GROUP_NAME") or "TPT测试日报群").strip()
# =========================


def get_token() -> str:
    r = httpx.get(
        "https://oapi.dingtalk.com/gettoken",
        params={"appkey": APP_KEY, "appsecret": APP_SECRET},
        timeout=20,
    )
    data = r.json()
    if data.get("errcode") != 0:
        raise RuntimeError(f"gettoken failed: {data}")
    return data["access_token"]


def userid_by_mobile(token: str, mobile: str) -> str:
    r = httpx.post(
        "https://oapi.dingtalk.com/topapi/v2/user/getbymobile",
        params={"access_token": token},
        json={"mobile": mobile},
        timeout=20,
    )
    data = r.json()
    if data.get("errcode") != 0:
        raise RuntimeError(
            f"getbymobile failed: {data}\n"
            "请确认：手机号正确、应用有通讯录权限、该用户在应用可见范围。"
        )
    result = data.get("result") or {}
    uid = result.get("userid") or ""
    if not uid:
        raise RuntimeError(f"no userid in: {data}")
    return uid


def create_chat(token: str, owner_userid: str, user_ids: list[str]) -> dict:
    """
    旧版创建会话：https://oapi.dingtalk.com/chat/create
    返回 chatid；再 convert 成 openConversationId。
    """
    # useridlist 须含群主
    ids = []
    for u in [owner_userid, *user_ids]:
        if u and u not in ids:
            ids.append(u)
    r = httpx.post(
        "https://oapi.dingtalk.com/chat/create",
        params={"access_token": token},
        json={
            "name": GROUP_NAME,
            "owner": owner_userid,
            "useridlist": ids,
            "showHistoryType": 1,
            "searchable": 0,
            "validationType": 0,
            "mentionAllAuthority": 0,
            "managementType": 0,
            "chatBannedType": 0,
        },
        timeout=30,
    )
    data = r.json()
    if data.get("errcode") != 0:
        raise RuntimeError(
            f"chat/create failed: {data}\n"
            "请在开放平台给应用开通「群会话」相关权限并发布版本；"
            "群主须在应用可见范围内。"
        )
    return data


def chatid_to_open_cid(token: str, chat_id: str) -> str:
    r = httpx.post(
        f"https://api.dingtalk.com/v1.0/im/chat/{chat_id}/convertToOpenConversationId",
        headers={"x-acs-dingtalk-access-token": token},
        timeout=20,
    )
    if r.status_code >= 400:
        # 有的环境 chatid 已可当 openConversationId 用，原样返回供人工试
        print("convert API 失败，将仅输出 chatid：", r.status_code, r.text[:300])
        return ""
    data = r.json()
    return (
        data.get("openConversationId")
        or data.get("open_conversation_id")
        or ""
    )


def main() -> None:
    if not APP_SECRET:
        raise SystemExit("请设置环境变量 DINGTALK_APP_SECRET")
    if not OWNER_MOBILE:
        raise SystemExit(
            "请设置环境变量 DINGTALK_OWNER_MOBILE=你的钉钉手机号（当群主）"
        )

    token = get_token()
    print("token ok")
    owner = userid_by_mobile(token, OWNER_MOBILE)
    print("owner userid =", owner)

    extra = [x.strip() for x in MEMBER_USER_IDS.split(",") if x.strip()]
    created = create_chat(token, owner, extra)
    chat_id = created.get("chatid") or created.get("chatId") or ""
    print("chat/create raw =", created)
    print("chatid =", chat_id)

    open_cid = chatid_to_open_cid(token, chat_id) if chat_id else ""
    print()
    print("========== 请保存 ==========")
    print("GROUP_NAME             =", GROUP_NAME)
    print("chatid                 =", chat_id)
    print("openConversationId     =", open_cid or "(convert 失败，可先试把 chatid 当 cid)")
    print("============================")
    print()
    print("下一步：")
    print("1. 钉钉里打开新群，把需要收日报的人拉进来")
    print("2. 群设置 → 机器人 → 添加「老丁」")
    print("3. 把 openConversationId 配进 .env：DINGTALK_OPEN_CONVERSATION_ID=...")


if __name__ == "__main__":
    main()
