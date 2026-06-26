"""启动：建表、默认锚点、Worker。"""

from __future__ import annotations

from sqlalchemy.engine import Engine

from app.platform.database import Base

from .models import AnchorNode, CleanJob, KnowledgeUnit, ParagraphUnit
from .utils import dumps_json
from .worker import start_background_tasks, stop_background_tasks


def ensure_data_cleaning_startup(engine: Engine) -> None:
    Base.metadata.create_all(
        bind=engine,
        tables=[
            AnchorNode.__table__,
            CleanJob.__table__,
            ParagraphUnit.__table__,
            KnowledgeUnit.__table__,
        ],
    )
    _seed_default_anchors(engine)


def _seed_default_anchors(engine: Engine) -> None:
    from sqlalchemy.orm import Session

    with Session(engine) as db:
        if db.query(AnchorNode).count() > 0:
            return
        defaults = [
            AnchorNode(
                id="login",
                label="登录",
                parent_id=None,
                synonyms_json=dumps_json(["登录", "注册登录", "用户登录"]),
                description="登录注册相关",
                sort_order=10,
            ),
            AnchorNode(
                id="login_sms",
                label="登录-短信验证码",
                parent_id="login",
                synonyms_json=dumps_json(["短信验证码", "SMS OTP", "验证码登录"]),
                description="短信验证码登录",
                sort_order=11,
            ),
            AnchorNode(
                id="order",
                label="订单",
                parent_id=None,
                synonyms_json=dumps_json(["订单", "下单", "交易"]),
                description="订单模块",
                sort_order=20,
            ),
            AnchorNode(
                id="api",
                label="接口",
                parent_id=None,
                synonyms_json=dumps_json(["API", "接口", "REST"]),
                description="接口说明",
                sort_order=30,
            ),
        ]
        db.add_all(defaults)
        db.commit()


async def on_startup() -> None:
    await start_background_tasks()


async def on_shutdown() -> None:
    await stop_background_tasks()
