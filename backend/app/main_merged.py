"""
main_merged.py - 合并后端入口

将 skill_hub 和 translate_server 合并到同一个端口：
  /api/*           → skill_hub 路由
  /translate/api/* → translate 路由（translate app 的 /api/* 被 mount 到 /translate）
  /*               → 前端 SPA 回落（返回 index.html）

两个原始后端代码完全不动。
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

from app.translate.app import app as translate_app, _dispatcher_loop, _janitor_loop, _recover_jobs_from_db

DIST_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


_translate_dispatcher_task = None
_translate_janitor_task = None


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    global _translate_dispatcher_task, _translate_janitor_task
    Base.metadata.create_all(bind=engine)
    _recover_jobs_from_db()
    _translate_dispatcher_task = asyncio.create_task(_dispatcher_loop())
    _translate_janitor_task = asyncio.create_task(_janitor_loop())
    yield
    if _translate_dispatcher_task:
        _translate_dispatcher_task.cancel()
    if _translate_janitor_task:
        _translate_janitor_task.cancel()


app = FastAPI(title="QA Platform Merged", version="3.0.0", lifespan=lifespan)

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


@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "merged"}


app.mount("/translate", translate_app)

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
