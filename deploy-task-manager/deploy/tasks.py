"""任务目录扫描与配置加载。

对外接口：
- get_task_dir(name) -> Path
- validate_task(name) -> dict  (含 expr, display_name, timeout)
- scan_available_tasks() -> list[dict]
- load_task_config(name) -> dict
"""

import json
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent

TASKS_ROOT = BASE_DIR / "tasks"


def get_task_dir(name: str) -> Path:
    """返回任务目录的绝对路径。"""
    return TASKS_ROOT / name


def load_task_config(name: str) -> dict:
    """读取任务目录下的 config.json，返回字典。文件不存在时返回空字典。"""
    cfg_path = get_task_dir(name) / "config.json"
    if not cfg_path.exists():
        return {}
    try:
        return json.loads(cfg_path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


def validate_task(name: str) -> dict:
    """校验任务目录是否存在、是否含 run.py，返回 spec 字典。

    spec 字段：
    - expr: cron 表达式（取自 config.json 的 trigger 字段）
    - display_name: 显示名（取自 config.json，回退为 name）
    - timeout: 超时秒数（取自 config.json，可选）
    """
    task_dir = get_task_dir(name)
    if not task_dir.is_dir():
        raise ValueError(f"任务目录不存在: {task_dir}")
    run_py = task_dir / "run.py"
    if not run_py.exists():
        raise ValueError(f"任务目录缺少 run.py: {task_dir}")

    cfg = load_task_config(name)
    expr = cfg.get("trigger") or cfg.get("expr")
    if not expr:
        raise ValueError(f"任务 {name} 缺少 trigger/expr 配置")
    display_name = cfg.get("display_name") or name
    timeout = cfg.get("timeout")

    return {
        "expr": expr,
        "display_name": display_name,
        "timeout": timeout,
    }


def scan_available_tasks() -> list[dict]:
    """扫描 tasks/ 目录，返回所有包含 run.py 的子目录列表。"""
    result = []
    if not TASKS_ROOT.is_dir():
        return result
    for item in sorted(TASKS_ROOT.iterdir()):
        if not item.is_dir():
            continue
        if not (item / "run.py").exists():
            continue
        cfg = load_task_config(item.name)
        result.append({
            "name": item.name,
            "display_name": cfg.get("display_name") or item.name,
            "expr": cfg.get("trigger") or cfg.get("expr") or "",
            "timeout": cfg.get("timeout"),
        })
    return result
