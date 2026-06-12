"""
main_merged.py - 合并后端入口

将 skill_hub 和 translate 合并到同一个端口：
  /api/*              → skill_hub / auth / changelog 路由
  /api/translate/*    → translate 路由
  /*                  → 前端 SPA 回落（返回 index.html）
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.core.config import CORS_ORIGINS
from app.core.database import engine, Base
from app.auth.router import router as auth_router, user_router
from app.skill_hub.skills_router import router as skill_router
from app.skill_hub.llm_router import router as llm_router
from app.skill_hub.integration_router import router as integration_router
from app.auth.models import User
from app.skill_hub.models import Skill, Branch, SkillVersion
from app.skill_hub.integration_service import ServiceAccount
from app.skill_hub.integration_models import LLMTask
from app.translate.models_db import TranslateJob
from app.changelog.models import ChangelogEntry
from app.changelog.router import router as changelog_router
from app.translate.router import router as translate_router
from app.translate.worker import start_background_tasks, stop_background_tasks

DIST_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


def assert_all_routes_protected(router):
    def collect_dep_names(dependant) -> set[str]:
        names = set()
        for d in dependant.dependencies:
            name = getattr(d.call, '__name__', None) or type(d.call).__name__
            names.add(name)
            names.update(collect_dep_names(d))
        return names

    for route in router.routes:
        if route.path in ("/health", "/api/health"):
            continue
        all_deps = collect_dep_names(route.dependant)
        if "get_user_for_request" not in all_deps and "RequireRole" not in all_deps:
            raise RuntimeError(
                f"[安全] 路由 {route.path} 缺少 get_user_for_request 依赖，"
                f"实际依赖: {all_deps}"
            )


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    Base.metadata.create_all(bind=engine)
    _migrate_translate_jobs(engine)
    await start_background_tasks()
    assert_all_routes_protected(translate_router)
    yield
    await stop_background_tasks()


def _migrate_translate_jobs(engine):
    import sqlite3
    db_path = str(engine.url).replace("sqlite:///", "")
    if not db_path:
        return
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(translate_jobs)")
    existing = {row[1] for row in cursor.fetchall()}
    for col in ("name", "username"):
        if col not in existing:
            cursor.execute(f"ALTER TABLE translate_jobs ADD COLUMN {col} VARCHAR DEFAULT ''")
    conn.commit()
    conn.close()


app = FastAPI(title="QA Platform Merged", version="3.0.0", lifespan=lifespan)


@app.middleware("http")
async def ensure_utf8_charset(request, call_next):
    response = await call_next(request)
    ct = response.headers.get("content-type", "")
    if "application/json" in ct and "charset" not in ct:
        response.headers["content-type"] = "application/json; charset=utf-8"
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(user_router)
app.include_router(skill_router)
app.include_router(llm_router)
app.include_router(integration_router)
app.include_router(changelog_router)
app.include_router(translate_router)


@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "merged"}


if (DIST_DIR / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=DIST_DIR / "assets"), name="static-assets")


@app.get("/", include_in_schema=False)
async def spa_root():
    if not (DIST_DIR / "index.html").exists():
        return {"hint": "前端未构建。请先构建前端，或开发模式启动 pnpm dev"}
    return FileResponse(DIST_DIR / "index.html", media_type="text/html")


@app.get("/{full_path:path}", include_in_schema=False)
async def spa_fallback(full_path: str):
    if full_path.startswith("api/"):
        raise HTTPException(404)
    if not (DIST_DIR / "index.html").exists():
        return {"hint": "前端未构建。请先构建前端，或开发模式启动 pnpm dev"}
    return FileResponse(DIST_DIR / "index.html", media_type="text/html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=48010)
