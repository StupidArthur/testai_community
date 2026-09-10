import asyncio
import json
import sys
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TASK_DIR))

try:
    from task_hooks import main, Callback
except ModuleNotFoundError:
    class Callback:
        def log(self, level, msg):
            print(f"[{level}] {msg}", flush=True)
        def status(self, msg):
            print(f"[status] {msg}", flush=True)
        def progress(self, pct, extra=""):
            print(f"[progress] {int(pct)}% {extra}", flush=True)
        def error(self, msg):
            print(f"[error] {msg}", flush=True)

    def main(run_fn):
        cb = Callback()
        try:
            result = run_fn(cb)
            print("\n=== 完成 ===")
            if result:
                print(result)
        except Exception as e:
            import traceback
            traceback.print_exc()
            sys.exit(1)

from backup_core import async_backup


def run(cb: Callback):
    result = asyncio.run(async_backup(cb))
    return json.dumps(result, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main(run)
