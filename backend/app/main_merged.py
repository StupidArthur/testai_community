"""
main_merged.py - 合并后端入口

将 skill_hub 和 translate_server 合并到同一个端口：
  /api/*           → skill_hub 路由
  /translate/api/* → translate 路由（translate app 的 /api/* 被 mount 到 /translate）

两个原始后端代码完全不动。
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

from app.core.database import engine, Base
from app.auth.router import router as auth_router, user_router
from app.skill_hub.skills_router import router as skill_router
from app.skill_hub.llm_router import router as llm_router
from app.skill_hub.integration_router import router as integration_router
from app.auth.models import User
from app.skill_hub.models import Skill, Branch, SkillVersion
from app.skill_hub.integration_service import ServiceAccount
from app.skill_hub.integration_models import LLMTask

Base.metadata.create_all(bind=engine)

from app.translate.app import app as translate_app

app = FastAPI(title="QA Platform Merged", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(user_router)
app.include_router(skill_router)
app.include_router(llm_router)
app.include_router(integration_router)


@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "merged"}


app.mount("/translate", translate_app)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=48010)
