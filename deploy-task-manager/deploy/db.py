"""SQLite 存储层。

对外接口：
- init_db(db_path=None)
- add_task(task) -> int
- update_task(task_id, fields) -> bool
- delete_task(task_id) -> bool
- get_task(task_id) -> dict | None
- list_tasks() -> list[dict]
- list_tasks_updated_after(ts) -> list[dict]
- start_run(task_id) -> int
- add_run_event(run_id, kind, value, message)
- finish_run(run_id, status, output, started_at)
- get_run(run_id) -> dict | None
- list_runs(task_id=None, limit=20) -> list[dict]
- list_run_events(run_id) -> list[dict]
"""

import json
import sqlite3
import time
import threading
from pathlib import Path

DEFAULT_DB = Path(__file__).parent / "tasks.db"
_LOCK = threading.Lock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    trigger_type TEXT NOT NULL,
    trigger_params TEXT NOT NULL,
    action_type TEXT NOT NULL,
    action_params TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    webhook_url TEXT NOT NULL DEFAULT '',
    updated_at REAL NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    output TEXT,
    started_at REAL NOT NULL,
    finished_at REAL
);
CREATE TABLE IF NOT EXISTS run_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    value TEXT,
    message TEXT,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_task ON runs(task_id);
CREATE INDEX IF NOT EXISTS idx_events_run ON run_events(run_id);
CREATE INDEX IF NOT EXISTS idx_tasks_updated ON tasks(updated_at);
"""

_conn = None


def _get_conn():
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(str(DEFAULT_DB), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.executescript(_SCHEMA)
        _conn.commit()
    return _conn


def init_db(db_path=None):
    """初始化数据库（默认使用项目目录下的 tasks.db，可显式指定路径）。"""
    global _conn, DEFAULT_DB
    if db_path:
        DEFAULT_DB = Path(db_path)
    _conn = sqlite3.connect(str(DEFAULT_DB), check_same_thread=False)
    _conn.row_factory = sqlite3.Row
    _conn.executescript(_SCHEMA)
    _conn.commit()
    return _conn


def _now():
    return time.time()


def _row_to_dict(row):
    d = dict(row)
    d["trigger_params"] = json.loads(d["trigger_params"])
    d["action_params"] = json.loads(d["action_params"])
    d["enabled"] = bool(d["enabled"])
    return d


def add_task(name, trigger_type, trigger_params, action_type, action_params, enabled=True, display_name="", webhook_url=""):
    """新增任务，返回新任务 id。trigger_params/action_params 为可 JSON 序列化字典。"""
    with _LOCK:
        conn = _get_conn()
        now = _now()
        cur = conn.execute(
            "INSERT INTO tasks (name, display_name, trigger_type, trigger_params, action_type, action_params, enabled, webhook_url, updated_at, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (name, display_name, trigger_type, json.dumps(trigger_params), action_type,
             json.dumps(action_params), int(enabled), webhook_url, now, now),
        )
        conn.commit()
        return cur.lastrowid


def update_task(task_id, fields):
    """按字典更新任务字段（key 必须是 tasks 表列名），自动刷新 updated_at。返回是否命中。"""
    if not fields:
        return False
    allowed = {"name", "display_name", "trigger_type", "trigger_params", "action_type", "action_params", "enabled", "webhook_url"}
    sets = []
    args = []
    for k, v in fields.items():
        if k not in allowed:
            raise ValueError(f"非法字段: {k}")
        if k in ("trigger_params", "action_params"):
            v = json.dumps(v)
        elif k == "enabled":
            v = int(v)
        sets.append(f"{k}=?")
        args.append(v)
    sets.append("updated_at=?")
    args.append(_now())
    args.append(task_id)
    with _LOCK:
        conn = _get_conn()
        cur = conn.execute(f"UPDATE tasks SET {', '.join(sets)} WHERE id=?", args)
        conn.commit()
        return cur.rowcount > 0


def delete_task(task_id):
    """删除任务（保留运行历史）。返回是否命中。"""
    with _LOCK:
        conn = _get_conn()
        cur = conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))
        conn.commit()
        return cur.rowcount > 0


def get_task(task_id):
    """按 id 查询任务，不存在返回 None。"""
    row = _get_conn().execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    return _row_to_dict(row) if row else None


def list_tasks():
    """列出全部任务。"""
    rows = _get_conn().execute("SELECT * FROM tasks ORDER BY id").fetchall()
    return [_row_to_dict(r) for r in rows]


def list_tasks_updated_after(ts):
    """列出 updated_at 晚于 ts 的任务，用于热更新 diff。"""
    rows = _get_conn().execute(
        "SELECT * FROM tasks WHERE updated_at > ? ORDER BY id", (ts,)
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_max_updated_at():
    """返回任务表最大 updated_at，无任务返回 0。"""
    row = _get_conn().execute("SELECT MAX(updated_at) AS m FROM tasks").fetchone()
    return row["m"] or 0


def start_run(task_id):
    """创建一次运行记录，状态为 running，返回 run_id。"""
    with _LOCK:
        conn = _get_conn()
        cur = conn.execute(
            "INSERT INTO runs (task_id, status, output, started_at) VALUES (?,?,?,?)",
            (task_id, "running", "", _now()),
        )
        conn.commit()
        return cur.lastrowid


def add_run_event(run_id, kind, value=None, message=None):
    """写入一条运行事件。kind: status/progress/log/error。value/message 转字符串存储。"""
    with _LOCK:
        conn = _get_conn()
        conn.execute(
            "INSERT INTO run_events (run_id, kind, value, message, created_at) VALUES (?,?,?,?,?)",
            (run_id, kind, str(value) if value is not None else None,
             message, _now()),
        )
        conn.commit()


def finish_run(run_id, status, output, started_at):
    """结束运行：更新状态、输出和耗时。"""
    with _LOCK:
        conn = _get_conn()
        conn.execute(
            "UPDATE runs SET status=?, output=?, finished_at=? WHERE id=?",
            (status, output, _now(), run_id),
        )
        conn.commit()


def get_run(run_id):
    """查询单条运行记录。"""
    row = _get_conn().execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
    return dict(row) if row else None


def list_runs(task_id=None, limit=20, offset=0):
    """查询运行历史，可按任务过滤，倒序分页。关联任务名返回。"""
    if task_id is not None:
        rows = _get_conn().execute(
            "SELECT runs.*, tasks.name AS task_name, tasks.display_name AS display_name"
            " FROM runs LEFT JOIN tasks ON runs.task_id = tasks.id"
            " WHERE runs.task_id=? ORDER BY runs.id DESC LIMIT ? OFFSET ?",
            (task_id, limit, offset),
        ).fetchall()
    else:
        rows = _get_conn().execute(
            "SELECT runs.*, tasks.name AS task_name, tasks.display_name AS display_name"
            " FROM runs LEFT JOIN tasks ON runs.task_id = tasks.id"
            " ORDER BY runs.id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
    return [dict(r) for r in rows]


def count_runs(task_id=None):
    """统计运行记录总数，可按任务过滤。"""
    if task_id is not None:
        row = _get_conn().execute(
            "SELECT COUNT(*) AS n FROM runs WHERE task_id=?", (task_id,)
        ).fetchone()
    else:
        row = _get_conn().execute("SELECT COUNT(*) AS n FROM runs").fetchone()
    return row["n"]


def list_run_events(run_id):
    """查询一次运行的全部事件，按时间正序。"""
    rows = _get_conn().execute(
        "SELECT * FROM run_events WHERE run_id=? ORDER BY id", (run_id,)
    ).fetchall()
    return [dict(r) for r in rows]
