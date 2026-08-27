# -*- mode: python ; coding: utf-8 -*-
# 由 build_exe.cmd 调用本文件打包。不要删除本 spec 再让 PyInstaller 现场生成，
# 否则会丢掉下面的 hiddenimports。main.py 同时 import packaging_deps 作为双保险。


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['uvicorn.logging', 'uvicorn.protocols', 'uvicorn.protocols.http', 'uvicorn.protocols.http.auto', 'uvicorn.protocols.websockets', 'uvicorn.protocols.websockets.auto', 'uvicorn.lifespan', 'uvicorn.lifespan.on', 'apscheduler.schedulers.background', 'apscheduler.triggers.cron', 'apscheduler.jobstores.memory', 'apscheduler.executors.pool', 'psutil', 'httptools', 'watchfiles', 'websockets',
        # tasks/ 下动态加载的任务代码依赖（双保险：packaging_deps.py 也会从入口 import）
        'httpx',            # alg_monitor: ding_api.py / alg_minio_monitor.py
        'boto3',            # alg_monitor: alg_minio_monitor.py (MinIO/RustFS)
        'botocore',         # alg_monitor: alg_minio_monitor.py
        'dotenv',           # alg_monitor: ding_api.py / ding_doc.py
        'packaging_deps',   # 入口采集模块
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='deploy-task-manager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
