"""
TestAI 日报：62 调度，HTTP 调用 64 推送接口。
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
from testai_push_client import trigger_push


def run(cb: Callback):
    cb.status("调用 64 TestAI 日报推送")
    cb.log("info", "POST /api/test-manage/push/daily")
    summary = trigger_push("daily")
    cb.log("info", summary)
    cb.progress(100, "完成")
    cb.status("完成")
    return summary


if __name__ == "__main__":
    main(run)
