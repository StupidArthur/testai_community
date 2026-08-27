"""
TestAI 周报：62 调度，调用 64 推送接口。
"""
import sys
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parent
ROOT = TASK_DIR.parent.parent
if str(TASK_DIR) not in sys.path:
    sys.path.insert(0, str(TASK_DIR))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from task_hooks import Callback, main

sys.path.insert(0, str(TASK_DIR.parent / "tm_daily_push"))
from testai_push_client import trigger_push


def run(cb: Callback):
    cb.status("调用 64 TestAI 周报推送")
    cb.log("info", "POST /api/test-manage/push/weekly")
    summary = trigger_push("weekly")
    cb.log("info", summary)
    cb.progress(100, "完成")
    cb.status("完成")
    return summary


if __name__ == "__main__":
    main(run)
