"""打包依赖采集模块。

tasks/ 下的 run.py 由 task_hooks 在运行时动态 import，PyInstaller 从 main.py
做静态分析时看不到这些文件里的第三方库。frozen exe 里一旦缺包，任务会在
import 阶段立刻失败（表现为运行报告耗时 0s，例如 ModuleNotFoundError: httpx）。

本模块由 main.py 显式 import，让分析器把下列库打进 exe。
运行时也会真正加载它们，保证调度进程内执行 alg_monitor 时能 import 成功。

不要在这里写业务逻辑；只放「动态任务需要、入口代码本身用不到」的第三方库。
"""

# alg_monitor: ding_api.py / alg_minio_monitor.py 调钉钉 OpenAPI、MinIO Console
import httpx  # noqa: F401

# alg_monitor: alg_minio_monitor.py 的 RustFS / S3 客户端
import boto3  # noqa: F401
import botocore  # noqa: F401

# alg_monitor: ding_api.py / ding_doc.py 读任务目录 .env
import dotenv  # noqa: F401
