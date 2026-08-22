"""任务动作执行器：进程内执行任务目录 run.py，回调驱动。

对外接口：
- execute_task(task) -> (run_id, status)
  从任务目录加载 run.py，调 run(cb)，实时写事件，收尾落历史。
"""

from pathlib import Path

import task_hooks
from tasks import get_task_dir


def execute_task(task):
    """执行任务，返回 (run_id, status)。task 为 db 任务记录（含 id/name）。"""
    name = task["name"]
    task_dir = get_task_dir(name)
    run_id, status, output = task_hooks.run_task(task["id"], name, task_dir)
    return run_id, status
