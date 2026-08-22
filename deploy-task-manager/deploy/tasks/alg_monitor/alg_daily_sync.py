"""
alg_daily_sync —— 每日算法更新同步到钉钉文档的业务逻辑。

钉钉文档结构：
  - Sheet1       → 配置表，列出所有环境（name / type / url / username / password / area）
  - <env name>   → 该环境的算法数据（4 列：算法模块 / 更新时间 / 责任人 / 更新原因）

流程（累积日志，最新在最上方）：
  1. 从 Sheet1 读环境配置列表
  2. 对每个环境：过滤 area + type，连数据源（minio/rustfs）拉近 24h 内更新的算法
  3. 读该环境 sheet 的全部历史行，建 (模块, 更新时间) 去重键
  4. 24h 候选项里凡是已在日志中的跳过，剩余按更新时间倒序作为“新事件”
  5. 新事件插到表头下方（第 2 行起），旧行整体下移、原样保留（含用户填的责任人/更新原因）
  6. 无新增则不写回

area 过滤：
  - config.json 的 area 字段限定本任务所属 area（本任务自包含，不依赖平台 env）
  - 未设置时处理全部 green+red 环境

独立于 task_manager，可单独 `python alg_daily_sync` 调用。
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

WORKSPACE_DIR = Path(__file__).resolve().parent


def _load_area() -> str:
    """从本任务 config.json 读 area；兼容旧环境变量 ALG_MONITOR_AREA。"""
    try:
        with open(WORKSPACE_DIR / "config.json", encoding="utf-8") as f:
            area = json.load(f).get("area", "")
        if isinstance(area, str) and area.strip():
            return area.strip()
    except Exception:
        pass
    return os.environ.get("ALG_MONITOR_AREA", "") or ""


TASK_AREA = _load_area()

if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

_env_file = WORKSPACE_DIR / ".env"
if _env_file.exists():
    for line in _env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

from ding_doc import DingTalkDoc
from alg_minio_monitor import AlgMinioMonitor, AlgRustfsMonitor

DOC_URL = "https://alidocs.dingtalk.com/i/nodes/P0MALyR8klkqRAOjFDPpL5M7W3bzYmDO"
HEADER = ["算法模块", "更新时间", "责任人", "更新原因"]
CONFIG_SHEET = "info"
CONFIG_HEADER = ["name", "type", "url", "username", "password", "area"]


# ---------- 内部 helper ----------

def _read_configs(dt: DingTalkDoc) -> list[dict]:
    """从 Sheet1 读所有环境配置。返回 list[dict]，跳过完全空行。"""
    rows = dt.read_xlsx(DOC_URL, "A1:Z100", sheet_name=CONFIG_SHEET)
    if len(rows) < 2:
        return []
    headers = rows[0]
    return [dict(zip(headers, r)) for r in rows[1:] if r and any(str(c).strip() for c in r)]


def _alg_name(full) -> str:
    """归一化算法模块名：去掉 resource/ 路径前缀，只保留模块文件名。"""
    full = str(full or "")
    prefix = "resource/"
    if full.startswith(prefix):
        return full[len(prefix):]
    return full


def _norm_time(s) -> str:
    """归一化时间字符串为 'YYYY-MM-DD HH:MM:SS'，兼容 - 与 / 分隔（钉钉回读常是 /）。
    无法解析时原样返回。"""
    s = str(s or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    return s


def _read_log(dt: DingTalkDoc, name: str) -> tuple[list[list[str]], set[tuple[str, str]]]:
    """读 per-env sheet 的累积日志，返回 (existing_rows, existing_keys)。

    existing_rows: list[[模块, 时间, 责任人, 更新原因]]，按 sheet 顺序（最新在上），
                   模块名/时间已归一化（剥 resource/ 前缀、时间统一 - 分隔）。
    existing_keys: {(norm_name, norm_time)}，用于去重，避免同一更新重复入日志。
    """
    existing_rows: list[list[str]] = []
    keys: set[tuple[str, str]] = set()
    rows = dt.read_xlsx(DOC_URL, "A1:D5000", sheet_name=name)
    if not rows or len(rows) < 2:
        return existing_rows, keys
    headers = rows[0]
    cols = {h: idx for idx, h in enumerate(headers)}
    name_idx = cols.get("算法模块")
    if name_idx is None:
        return existing_rows, keys
    time_idx = cols.get("更新时间")
    owner_idx = cols.get("责任人")
    reason_idx = cols.get("更新原因")
    for row in rows[1:]:
        if not any(str(c).strip() for c in row if c is not None):
            continue  # 跳过空行
        n = str(row[name_idx]) if len(row) > name_idx and row[name_idx] else ""
        if not n:
            continue
        t = str(row[time_idx]) if time_idx is not None and len(row) > time_idx and row[time_idx] else ""
        owner = str(row[owner_idx]) if owner_idx is not None and len(row) > owner_idx and row[owner_idx] else ""
        reason = str(row[reason_idx]) if reason_idx is not None and len(row) > reason_idx and row[reason_idx] else ""
        nn = _alg_name(n)
        nt = _norm_time(t)
        existing_rows.append([nn, nt, owner, reason])
        keys.add((nn, nt))
    return existing_rows, keys


def _build_monitor(cfg: dict):
    """根据 type 构建数据源监控客户端（minio/rustfs）。"""
    mtype = cfg.get("type")
    if mtype == "minio":
        return AlgMinioMonitor(cfg["url"], cfg["username"], cfg["password"])
    if mtype == "rustfs":
        return AlgRustfsMonitor(cfg["url"], cfg["username"], cfg["password"])
    raise ValueError(f"unsupported type: {mtype}")


def _probe(mon) -> bool:
    """调用对应后端的鉴权探活方法（MinIO=login / RustFS=connect）。"""
    if isinstance(mon, AlgRustfsMonitor):
        return mon.connect()
    return mon.login()


def _sync_one(dt: DingTalkDoc, cfg: dict) -> list[str] | str | None:
    """同步单个环境。返回 list[新增算法名] / str 跳过原因 / None 失败。"""
    name = cfg.get("name")
    if not name:
        return None
    if cfg.get("area") not in ("green", "red"):
        return "skip_area"
    if TASK_AREA and cfg.get("area") != TASK_AREA:
        return "skip_mismatch"
    if cfg.get("type") not in ("minio", "rustfs"):
        return "skip_type"

    existing_rows, existing_keys = _read_log(dt, name)

    mon = _build_monitor(cfg)
    with mon:
        if not _probe(mon):
            raise RuntimeError(f"{cfg.get('type')} 鉴权失败")
        all_files = mon.get_alg_info_in_one_day()

    files = [f for f in all_files if not f.is_dir]
    files.sort(key=lambda f: _norm_time(f.last_modified), reverse=True)

    new_rows: list[list[str]] = []
    for f in files:
        alg_name = _alg_name(f.name)
        t = _norm_time(f.last_modified)
        if (alg_name, t) in existing_keys:
            continue  # 该更新已入日志，跳过
        new_rows.append([alg_name, t, "", ""])
        existing_keys.add((alg_name, t))  # 防同批次重复

    new_names = [r[0] for r in new_rows]
    if not new_names:
        return []  # 无新增，保持 sheet 原样不写回

    all_rows = [HEADER] + new_rows + existing_rows
    end_row = len(all_rows)
    dt.write_xlsx(DOC_URL, f"A1:D{end_row}", all_rows, sheet_name=name)
    return new_names


# ---------- 对外接口 ----------

def sync_all_envs(on_env=None, on_log=None) -> int:
    """同步 Sheet1 配置表里所有环境。

    参数:
      on_env:  每环境处理完调用 on_env(i, total, name, result)
      on_log:  异常回调 on_log(name, level, message)，level: info/warn/error

    返回: int 总新增条数。
    """
    dt = DingTalkDoc()
    configs = _read_configs(dt)
    total_files = 0
    for i, cfg in enumerate(configs, start=1):
        name = cfg.get("name") or f"row{i}"
        try:
            result = _sync_one(dt, cfg)
        except Exception as e:
            if on_log:
                on_log(name, "error", f"{type(e).__name__}: {e}")
            result = None
        if on_env:
            on_env(i, len(configs), name, result)
        if isinstance(result, list):
            total_files += len(result)
    return total_files


if __name__ == "__main__":
    print(sync_all_envs())