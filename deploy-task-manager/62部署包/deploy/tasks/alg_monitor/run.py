"""
alg_monitor 任务入口：调度服务调度的算法版本同步任务。

业务逻辑同目录下 alg_daily_sync.py，自包含（不带外部依赖）。
"""
import sys
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parent
TASK_MANAGER_DIR = TASK_DIR.parent.parent

if str(TASK_DIR) not in sys.path:
    sys.path.insert(0, str(TASK_DIR))
if str(TASK_MANAGER_DIR) not in sys.path:
    sys.path.insert(0, str(TASK_MANAGER_DIR))

from task_hooks import main, Callback
from alg_daily_sync import sync_all_envs, DOC_URL


def run(cb: Callback):
    cb.status("开始采集")
    detail: list[str] = []  # 每环境一行：name 新增 N: 算法1, 算法2

    def on_env(i: int, total: int, name: str, result):
        cb.progress(5 + int(85 * i / max(total, 1)), f"处理 {name}")
        if isinstance(result, list):
            names = ", ".join(result)
            line = f"env {name} 新增 {len(result)} 条" + (f": {names}" if result else "")
            cb.log("info", line)
            detail.append(line)
        elif result == "skip_area":
            cb.log("info", f"{name} area 配置无效 跳过")
        elif result == "skip_mismatch":
            cb.log("info", f"{name} 与本任务 area 不匹配 跳过")
        elif result == "skip_type":
            cb.log("warn", f"{name} type 暂不支持")
        else:
            cb.log("error", f"{name} 失败")

    def on_log(name: str, level: str, message: str):
        cb.log(level, f"[{name}] {message}")

    total = sync_all_envs(on_env=on_env, on_log=on_log)
    cb.progress(100, "完成")
    body = "\n".join(detail)
    return f"采集完成，新增 {total} 条\n{body}\n\n文档: {DOC_URL}"


if __name__ == "__main__":
    main(run)