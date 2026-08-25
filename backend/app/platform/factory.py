"""
platform.factory — FastAPI 应用装配入口（组合根）。

职责：
  - 创建 FastAPI 实例
  - 按 platform.registry.APPS 注册各业务模块
  - lifespan、中间件、SPA 静态回落、/api/health
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.platform.config import CORS_ORIGINS, BACKEND_PORT
from app.platform.database import engine, Base
from app.platform.route_guard import assert_router_protected
from app.platform.registry import APPS

# backend/app/platform/factory.py → 项目根 = parents[3]
DIST_DIR = Path(__file__).resolve().parents[3] / "frontend" / "dist"


def create_app() -> FastAPI:
    """创建并装配 TestAI Community 后端应用。"""

    @asynccontextmanager
    async def lifespan(app_instance: FastAPI):
        for mod in APPS:
            mod.import_models()
        Base.metadata.create_all(bind=engine)

        for mod in APPS:
            if mod.startup_sync is not None:
                mod.startup_sync(engine)

        for mod in APPS:
            if mod.startup_async is not None:
                await mod.startup_async()

        for mod in APPS:
            if mod.router is not None:
                assert_router_protected(mod.router, label=mod.guard_label())

        yield

        for mod in reversed(APPS):
            if mod.shutdown_async is not None:
                await mod.shutdown_async()

    application = FastAPI(
        title="TestAI Community",
        version="3.0.0",
        lifespan=lifespan,
    )

    @application.middleware("http")
    async def ensure_utf8_charset(request, call_next):
        response = await call_next(request)
        ct = response.headers.get("content-type", "")
        if "application/json" in ct and "charset" not in ct:
            response.headers["content-type"] = "application/json; charset=utf-8"
        return response

    application.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    for mod in APPS:
        if mod.router is not None:
            application.include_router(mod.router)

    @application.get("/api/health")
    def health_check():
        return {"status": "ok", "service": "testai-community"}

    if (DIST_DIR / "assets").is_dir():
        application.mount(
            "/assets",
            StaticFiles(directory=DIST_DIR / "assets"),
            name="static-assets",
        )

    # Vite public/ 下的静态资源（如 docs/*.md 使用说明下载）——须在 SPA 兜底路由前挂载
    if (DIST_DIR / "docs").is_dir():
        application.mount(
            "/docs",
            StaticFiles(directory=DIST_DIR / "docs"),
            name="static-docs",
        )

    @application.get("/", include_in_schema=False)
    async def spa_root():
        if not (DIST_DIR / "index.html").exists():
            return {"hint": "前端未构建。请先构建前端，或开发模式启动 pnpm dev"}
        return FileResponse(DIST_DIR / "index.html", media_type="text/html")

    @application.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(404)
        if not (DIST_DIR / "index.html").exists():
            return {"hint": "前端未构建。请先构建前端，或开发模式启动 pnpm dev"}
        return FileResponse(DIST_DIR / "index.html", media_type="text/html")

    return application


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=BACKEND_PORT)
