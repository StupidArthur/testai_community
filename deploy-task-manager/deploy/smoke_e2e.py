"""端到端冒烟：验证动态任务可加载、平台 API 可用，且不触发真实副作用。

不会：执行 run_task / 发钉钉运行报告 / 调 64 推送 / 写钉钉文档。
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

DEPLOY_ROOT = Path(__file__).resolve().parent
if str(DEPLOY_ROOT) not in sys.path:
    sys.path.insert(0, str(DEPLOY_ROOT))

EXPECTED_TASKS = (
    "alg_monitor",
    "demo_task",
    "health_check",
    "tm_daily_push",
    "tm_weekly_push",
)


def run_smoke():
    """跑完全部检查；任一步失败抛异常。无命令行参数。"""
    results = []

    def step(name: str, ok: bool, detail: str = ""):
        results.append((name, ok, detail))
        status = "OK" if ok else "FAIL"
        print(f"[{status}] {name}" + (f"  {detail}" if detail else ""))
        if not ok:
            raise AssertionError(f"{name}: {detail}")

    # 1. 打包依赖在进程内可导入（对应 62 上的 httpx 缺失）
    import packaging_deps  # noqa: F401
    import httpx
    import boto3
    import botocore
    import dotenv

    client = httpx.Client(timeout=5)
    client.close()
    step("packaging_deps", True, f"httpx={httpx.__version__}")

    # 2. 打包脚本不再删除 spec
    build_cmd = (DEPLOY_ROOT / "build_exe.cmd").read_text(encoding="utf-8")
    spec_text = (DEPLOY_ROOT / "deploy-task-manager.spec").read_text(encoding="utf-8")
    step(
        "build_exe_keeps_spec",
        "del deploy-task-manager.spec" not in build_cmd
        and "deploy-task-manager.spec" in build_cmd,
        "cmd uses spec and does not delete it",
    )
    step(
        "spec_has_httpx",
        "'httpx'" in spec_text and "packaging_deps" in spec_text,
        "hiddenimports include httpx + packaging_deps",
    )

    # 3. 入口会采集依赖
    main_src = (DEPLOY_ROOT / "main.py").read_text(encoding="utf-8")
    step("main_imports_packaging_deps", "import packaging_deps" in main_src)

    import db
    import tasks as task_repo
    import task_hooks
    from scheduler import build_trigger
    from app import create_app

    db.init_db()

    # 4. 扫描任务目录，五个业务目录都在
    available = {t["name"]: t for t in task_repo.scan_available_tasks()}
    missing = [n for n in EXPECTED_TASKS if n not in available]
    step("scan_available_tasks", not missing, json.dumps(sorted(available), ensure_ascii=False))

    # 5. 与调度器相同路径：动态加载每个 run.py，不调用 run()
    for name in EXPECTED_TASKS:
        module = task_hooks._load_run_module(task_repo.get_task_dir(name))
        has_run = callable(getattr(module, "run", None))
        step(f"load_run:{name}", has_run, f"file={module.__file__}")

    # 6. 复现原故障路径：alg_monitor 链路必须能 import httpx
    alg_dir = task_repo.get_task_dir("alg_monitor")
    sys.path.insert(0, str(alg_dir))
    import ding_api
    import ding_doc
    import alg_minio_monitor
    import alg_daily_sync

    step("alg_monitor.ding_api_httpx", ding_api.httpx is httpx or hasattr(ding_api, "httpx"))
    api = ding_api.DingTalkAPI(app_key="dummy", app_secret="dummy", operator_id="dummy")
    step("alg_monitor.DingTalkAPI_client", type(api._client).__name__ == "Client")
    api._client.close()
    step(
        "alg_monitor.minio_has_httpx",
        hasattr(alg_minio_monitor, "httpx"),
        f"boto3={boto3.__version__}",
    )
    step("alg_monitor.sync_all_envs_exists", callable(alg_daily_sync.sync_all_envs))
    step("alg_monitor.DingTalkDoc_import", ding_doc.DingTalkDoc is not None)

    # 7. 其它任务模块可导入（不发 HTTP）
    daily_dir = task_repo.get_task_dir("tm_daily_push")
    if str(daily_dir) not in sys.path:
        sys.path.insert(0, str(daily_dir))
    import testai_push_client

    step("tm_daily_push.client_import", callable(testai_push_client.trigger_push))

    demo = task_hooks._load_run_module(task_repo.get_task_dir("demo_task"))
    payload = {
        "task_name": "demo_task",
        "display_name": "演示",
        "run_id": 0,
        "status": "success",
        "output": "ok",
        "started_at": time.time(),
        "duration_sec": 1,
        "platform_name": "smoke",
    }
    msg = demo.build_webhook(payload)
    step("demo_task.build_webhook", msg.get("msgtype") == "markdown")
    default_msg = task_hooks._default_webhook(payload, "task-mgr")
    step(
        "default_webhook_text",
        default_msg.get("msgtype") == "text"
        and "运行报告" in default_msg["text"]["content"],
    )

    # 8. health_check 诊断只读 DB，不发群
    hc = task_hooks._load_run_module(task_repo.get_task_dir("health_check"))
    diagnosis = hc.diagnose()
    step(
        "health_check.diagnose",
        diagnosis.get("verdict") in ("正常", "警告", "异常"),
        json.dumps(diagnosis.get("tasks"), ensure_ascii=False),
    )

    # 9. cron 构造（Unix 0=周日转换）仍可用
    dummy = {"trigger_params": {"expr": "50 23 * * *"}}
    trigger = build_trigger(dummy)
    step("scheduler.build_trigger", trigger is not None, str(trigger))

    # 10. HTTP API（TestClient，不起真实端口、不 POST /run）
    from fastapi.testclient import TestClient

    app = create_app()
    with TestClient(app) as tc:
        platform = tc.get("/api/platform")
        step("api.platform", platform.status_code == 200, platform.json().get("name", ""))
        avail = tc.get("/api/available")
        names = [t["name"] for t in avail.json().get("tasks", [])]
        step("api.available", avail.status_code == 200 and "alg_monitor" in names)
        tasks_resp = tc.get("/api/tasks")
        step("api.tasks", tasks_resp.status_code == 200, f"n={len(tasks_resp.json().get('tasks', []))}")
        runs_resp = tc.get("/api/runs?limit=5")
        step("api.runs", runs_resp.status_code == 200)
        cfg = tc.get("/api/available/alg_monitor/config")
        step("api.alg_monitor.config", cfg.status_code == 200, cfg.json().get("config", {}).get("display_name", ""))

    print(f"\n全部通过：{len(results)} 项。未执行任务、未发 webhook、未写钉钉文档。")
    return results


if __name__ == "__main__":
    run_smoke()
