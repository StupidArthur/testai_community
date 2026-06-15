"""
platform.registry — 全站业务 App 注册表。

新增 App 时：在此追加 AppModule，实现 router / models / 可选 lifespan 钩子；
factory 只循环 APPS，不再逐个 import bootstrap。
"""

from __future__ import annotations

from app.auth import bootstrap as auth_bootstrap
from app.auth.models import User
from app.auth.router import router as auth_router

from app.skill_hub import bootstrap as skill_hub_bootstrap
from app.skill_hub.models import Branch, Skill, SkillCategory, SkillVersion
from app.skill_hub.skills_router import router as skill_router

from app.translate import bootstrap as translate_bootstrap
from app.translate.models_db import TranslateJob
from app.translate.router import router as translate_router

from app.external_api.models import LLMTask, ServiceAccount
from app.external_api.router import router as external_api_router

from app.platform.changelog.models import ChangelogEntry
from app.platform.changelog.router import router as changelog_router

from app.platform.app_module import AppModule


APPS: tuple[AppModule, ...] = (
    AppModule(
        name="auth",
        router=auth_router,
        models=(User,),
        startup_sync=lambda _engine: auth_bootstrap.ensure_default_admin(),
    ),
    AppModule(
        name="skills",
        router=skill_router,
        models=(Skill, SkillCategory, Branch, SkillVersion),
        startup_sync=skill_hub_bootstrap.ensure_skill_hub_startup,
    ),
    AppModule(
        name="external_api",
        router=external_api_router,
        models=(ServiceAccount, LLMTask),
    ),
    AppModule(
        name="platform.changelog",
        router=changelog_router,
        models=(ChangelogEntry,),
    ),
    AppModule(
        name="translate",
        router=translate_router,
        models=(TranslateJob,),
        startup_sync=translate_bootstrap.migrate_schema,
        startup_async=translate_bootstrap.on_startup,
        shutdown_async=translate_bootstrap.on_shutdown,
    ),
)
