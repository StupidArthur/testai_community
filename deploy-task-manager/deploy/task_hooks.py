"""任务执行钩子：进程内加载 run.py，回调驱动事件记录与钉钉推送。

对外接口：
- Callback           任务回调对象（status / log / progress / error）
- run_task(task_id, name, task_dir) -> (run_id, status, output)
- main(run_fn)       CLI 独立运行入口
"""

import json
import os
import sys
import time
import importlib.util
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

import db

# 确保 deploy 根目录在 sys.path 中，使 run.py 能 import task_hooks
if getattr(sys, "frozen", False):
    _DEPLOY_ROOT = Path(sys.executable).parent
else:
    _DEPLOY_ROOT = Path(__file__).resolve().parent
if str(_DEPLOY_ROOT) not in sys.path:
    sys.path.insert(0, str(_DEPLOY_ROOT))


class Callback:
    """任务运行回调：将事件实时写入 DB run_events 表。"""

    def __init__(self, run_id: int):
        self._run_id = run_id

    def status(self, text: str):
        db.add_run_event(self._run_id, "status", message=text)

    def log(self, level: str, message: str):
        db.add_run_event(self._run_id, "log", value=level, message=message)

    def progress(self, percent: int, desc: str = ""):
        db.add_run_event(self._run_id, "progress", value=percent, message=desc)

    def error(self, message: str):
        db.add_run_event(self._run_id, "error", message=message)


def _load_run_module(task_dir: Path):
    """用 importlib 从指定路径加载 run.py 模块，避免同名冲突。"""
    run_py = task_dir / "run.py"
    # 把 task_dir 加入 sys.path，使 run.py 内的本地 import 生效
    task_dir_str = str(task_dir)
    if task_dir_str not in sys.path:
        sys.path.insert(0, task_dir_str)

    # 清除可能已缓存的 run 模块（来自其他任务）
    for mod_name in list(sys.modules.keys()):
        if mod_name == "run":
            del sys.modules[mod_name]

    spec = importlib.util.spec_from_file_location("run", str(run_py))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _send_webhook(task_name, display_name, run_id, status, output, started_at, duration_sec, task_dir):
    """发送钉钉 webhook 推送。"""
    # 读取任务 config.json 获取 webhook 配置
    cfg_path = task_dir / "config.json"
    cfg = {}
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
        except Exception:
            pass

    wh = cfg.get("webhook") or {}
    webhook_url = str(wh.get("url") or "").strip()
    if not webhook_url:
        webhook_url = os.environ.get("PLATFORM_WEBHOOK_URL", "").strip()
    if not webhook_url:
        return

    keyword = str(wh.get("keyword") or "").strip()
    if not keyword:
        keyword = os.environ.get("DINGTALK_KEYWORD", "task-mgr").strip()

    platform_name = os.environ.get("PLATFORM_NAME", "定时任务管理平台")

    payload = {
        "task_name": task_name,
        "display_name": display_name,
        "run_id": run_id,
        "status": status,
        "output": output or "",
        "started_at": started_at,
        "duration_sec": duration_sec,
        "platform_name": platform_name,
    }

    # 尝试加载任务自定义推送模板
    try:
        run_module = _load_run_module(task_dir)
        build_webhook = getattr(run_module, "build_webhook", None)
    except Exception:
        build_webhook = None

    if callable(build_webhook):
        try:
            msg = build_webhook(payload)
        except Exception as e:
            msg = _default_webhook(payload, keyword)
    else:
        msg = _default_webhook(payload, keyword)

    # 确保 keyword 出现在消息文本中（钉钉安全设置要求）
    _ensure_keyword(msg, keyword)

    try:
        data = json.dumps(msg, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(webhook_url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
    except Exception:
        pass


def _default_webhook(payload, keyword):
    """默认钉钉推送模板。"""
    ok = payload["status"] == "success"
    label = "成功" if ok else "失败"
    started = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(payload["started_at"]))
    out = (payload.get("output") or "").strip() or "（无输出）"
    if len(out) > 500:
        out = out[:500] + "…"
    text = (
        f"【{keyword}】{payload['display_name']} · 运行报告\n"
        f"状态: {'✅ 成功' if ok else '❌ 失败'}  耗时: {int(payload['duration_sec'])}s\n"
        f"记录于: {started}\n"
        f"任务: {payload['task_name']}  运行号: {payload['run_id']}\n"
        f"平台: {payload['platform_name']}\n"
        f"输出摘要:\n{out}"
    )
    return {"msgtype": "text", "text": {"content": text}}


def _ensure_keyword(msg, keyword):
    """确保 keyword 出现在消息文本中。"""
    if not keyword:
        return
    if msg.get("msgtype") == "text":
        content = msg.get("text", {}).get("content", "")
        if keyword not in content:
            msg["text"]["content"] = f"【{keyword}】{content}"
    elif msg.get("msgtype") == "markdown":
        text = msg.get("markdown", {}).get("text", "")
        if keyword not in text:
            msg["markdown"]["text"] = f"**{keyword}**\n\n{text}"


def run_task(task_id: int, name: str, task_dir: Path):
    """执行任务，返回 (run_id, status, output)。

    流程：创建运行记录 → 加载 run.py → 调 run(cb) → 记录事件 → 收尾 → 推送 webhook。
    """
    task_dir = Path(task_dir)
    run_id = db.start_run(task_id)
    started_at = time.time()
    cb = Callback(run_id)

    # 加载任务配置获取 display_name
    cfg_path = task_dir / "config.json"
    display_name = name
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
            display_name = cfg.get("display_name") or name
        except Exception:
            pass

    status = "failed"
    output = ""

    try:
        module = _load_run_module(task_dir)
        run_fn = getattr(module, "run", None)
        if not callable(run_fn):
            raise ValueError(f"任务 {name} 的 run.py 缺少 run(cb) 函数")

        result = run_fn(cb)
        status = "success"
        output = str(result) if result is not None else ""
    except Exception as e:
        status = "failed"
        output = f"{type(e).__name__}: {e}"
        cb.error(output)
    finally:
        duration = time.time() - started_at
        db.finish_run(run_id, status, output, started_at)

    # 异步发送 webhook（不阻塞调度）
    try:
        _send_webhook(name, display_name, run_id, status, output, started_at, duration, task_dir)
    except Exception:
        pass

    return run_id, status, output


def main(run_fn):
    """CLI 独立运行入口：python run.py 时直接调用。"""
    class ConsoleCallback:
        def status(self, text):
            print(f"[STATUS] {text}")

        def log(self, level, message):
            print(f"[{level.upper()}] {message}")

        def progress(self, percent, desc=""):
            print(f"[PROGRESS] {percent}% {desc}")

        def error(self, message):
            print(f"[ERROR] {message}")

    cb = ConsoleCallback()
    try:
        result = run_fn(cb)
        print(f"\n===== 完成 =====")
        print(result)
    except Exception as e:
        print(f"\n===== 失败 =====")
        print(f"{type(e).__name__}: {e}")
        sys.exit(1)
