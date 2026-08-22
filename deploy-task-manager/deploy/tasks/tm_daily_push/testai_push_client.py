"""
调用 64 上 TestAI 推送 API（登录 + daily/weekly）。

配置：只读本目录及同级周报目录的 .env 文件（不读平台进程环境变量）。

  日报：tm_daily_push/.env
  周报：tm_daily_push/.env + tm_weekly_push/.env（后者覆盖同名键）

字段：
  TESTAI_BASE_URL / TESTAI_PUSH_USER / TESTAI_PUSH_PASS
  TESTAI_DRY_RUN=false  才真发；true 只预览
  TESTAI_FORCE=false    平时保持 false
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

_CLIENT_DIR = Path(__file__).resolve().parent
_WEEKLY_ENV = _CLIENT_DIR.parent / "tm_weekly_push" / ".env"


def _parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    text = path.read_text(encoding="utf-8-sig")
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _load_settings(kind: str) -> dict[str, str]:
    merged: dict[str, str] = {}
    daily_env = _CLIENT_DIR / ".env"
    merged.update(_parse_env_file(daily_env))
    if kind == "weekly":
        merged.update(_parse_env_file(_WEEKLY_ENV))
    return merged


def _truthy(raw: str | None, default: bool = False) -> bool:
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "y", "on")


def _http_json(method: str, url: str, body: dict | None = None, token: str | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} {url}: {detail}") from exc


def trigger_push(kind: str) -> str:
    """kind: daily | weekly。只接收这一个参数，避免与旧 run.py / 新客户端混用报错。"""
    if kind not in ("daily", "weekly"):
        raise ValueError(f"kind 必须是 daily/weekly，收到: {kind}")

    cfg = _load_settings(kind)
    env_path = _CLIENT_DIR / ".env"
    if kind == "weekly" and _WEEKLY_ENV.exists():
        env_path = _WEEKLY_ENV
    if not (_CLIENT_DIR / ".env").exists() and not _WEEKLY_ENV.exists():
        raise RuntimeError(
            f"找不到 .env。请创建: {_CLIENT_DIR / '.env'}"
        )

    base = (cfg.get("TESTAI_BASE_URL") or "http://10.30.144.64:48011").rstrip("/")
    user = (cfg.get("TESTAI_PUSH_USER") or "manager").strip()
    password = (cfg.get("TESTAI_PUSH_PASS") or "").strip()
    if not password:
        raise RuntimeError("未配置 TESTAI_PUSH_PASS（写在任务目录 .env）")

    dry_run = _truthy(cfg.get("TESTAI_DRY_RUN"), False)
    force = _truthy(cfg.get("TESTAI_FORCE"), False)

    login = _http_json(
        "POST",
        f"{base}/api/auth/login",
        {"username": user, "password": password},
    )
    token = login.get("access_token")
    if not token:
        raise RuntimeError(f"登录失败，无 access_token: {login}")

    result = _http_json(
        "POST",
        f"{base}/api/test-manage/push/{kind}",
        {"dry_run": dry_run, "force": force},
        token=token,
    )

    return (
        f"kind={kind} period={result.get('period_key')} "
        f"sent={result.get('sent')} skipped={result.get('skipped')} "
        f"dry_run={result.get('dry_run')} local_dry_run={dry_run} "
        f"bytes={result.get('message_bytes')} reason={result.get('reason') or ''} "
        f"env={env_path}"
    )
