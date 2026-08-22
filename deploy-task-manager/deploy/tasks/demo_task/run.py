import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from task_hooks import main, Callback


def run(cb: Callback):
    cb.status("开始处理")
    cb.log("info", "任务已启动")
    for i in range(5):
        time.sleep(1)
        cb.progress((i + 1) * 20, f"处理第 {i + 1} 批")
    cb.log("info", "全部批处理完成")
    cb.status("完成")
    return "demo_task 全部处理完毕"


def build_webhook(payload):
    """自定义推送模板：任务级 webhook 演示。关键词由平台统一兜底注入。"""
    ok = payload.get("status") == "success"
    label = "成功" if ok else "失败"
    started = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(payload["started_at"]))
    out = (payload.get("output") or "").strip() or "（无输出）"
    if len(out) > 400:
        out = out[:400] + "…"
    text = (
        f"> 📊 **{payload['display_name']} · 运行报告**\n"
        f">\n"
        f"> 记录于 `{started}`\n\n"
        f"**状态**: {'✅ 成功' if ok else '❌ 失败'}　**耗时**: {int(payload['duration_sec'])}s\n\n"
        f"**输出摘要**\n"
        f"```\n{out}\n```\n\n"
        f"---\n\n"
        f"- 🆔 任务 `{payload['task_name']}`\n"
        f"- 🏷 显示名 **{payload['display_name']}**\n"
        f"- 🔗 运行号 `{payload['run_id']}`\n"
        f"- 📡 来源 {payload['platform_name']}\n\n"
        f"*本条为自定义推送模板，演示任务级 build_webhook 能力*"
    )
    return {
        "msgtype": "markdown",
        "markdown": {"title": f"{payload['display_name']} - {label}", "text": text},
    }


if __name__ == "__main__":
    main(run)
