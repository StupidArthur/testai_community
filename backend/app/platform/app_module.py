"""业务 App 在 platform.factory 中的注册描述（组合根协议）。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from fastapi import APIRouter
from sqlalchemy.engine import Engine

# startup_sync(engine) — 进程启动时同步钩子（建表之后）
StartupSyncHook = Callable[[Engine], None]
# startup_async / shutdown_async — 进程启停异步钩子
StartupAsyncHook = Callable[[], Awaitable[None]]
ShutdownAsyncHook = Callable[[], Awaitable[None]]


@dataclass(frozen=True)
class AppModule:
    """
    单个业务 App 在 factory 中的装配项。

    factory 统一：注册 Router、import Models 建表、route_guard、lifespan 钩子。
    各 App 仅在 registry.APPS 中声明差异（如 translate 的 worker 启停）。
    """

    name: str
    router: APIRouter | None = None
    route_guard_label: str | None = None
    models: tuple[type, ...] = field(default_factory=tuple)
    startup_sync: StartupSyncHook | None = None
    startup_async: StartupAsyncHook | None = None
    shutdown_async: ShutdownAsyncHook | None = None

    def guard_label(self) -> str:
        return self.route_guard_label or self.name

    def import_models(self) -> None:
        """确保 ORM 类已加载到 Base.metadata（registry 构建时已 import，此处为显式文档用途）。"""
        _ = self.models
