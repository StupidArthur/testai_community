"""
pytest 配置：强制使用独立测试库与测试数据目录，不污染 A 开发环境。

必须在 import app 之前设置环境变量（load_dotenv 不会覆盖已存在的 env）。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
TEST_DB = BACKEND_DIR / "database_test.sqlite"
TEST_DATA_DIR = BACKEND_DIR / "tests" / ".data"

# 测试专用库与 Translate 目录（与 database_dev / database_prod 隔离）
os.environ["DATABASE_URL"] = "sqlite:///" + str(TEST_DB.resolve()).replace("\\", "/")
os.environ["TRANSLATE_UPLOAD_DIR"] = str((TEST_DATA_DIR / "uploads").resolve())
os.environ["TRANSLATE_RESULT_DIR"] = str((TEST_DATA_DIR / "results").resolve())
os.environ["TOOL_HUB_ARTIFACT_DIR"] = str((TEST_DATA_DIR / "tool_artifacts").resolve())
os.environ["KNOWLEDGE_BASE_DATA_DIR"] = str((TEST_DATA_DIR / "knowledge_base").resolve())
os.environ["KNOWLEDGE_BASE_CHROMA_DIR"] = str((TEST_DATA_DIR / "knowledge_base" / "chroma").resolve())
os.environ.setdefault("ENV", "dev")
# 测试禁用企微定时推送，避免后台轮询干扰
os.environ["WECOM_PUSH_ENABLED"] = "false"
os.environ["WECOM_WEBHOOK_URL"] = ""
# 测试默认关闭日更 19:50 锁定（专项用例可 monkeypatch 再打开）
os.environ["TM_DAILY_EDIT_LOCK_DISABLED"] = "1"

sys.path.insert(0, str(BACKEND_DIR))

import pytest
from app.platform.factory import app
from app.platform.database import engine, Base
from app.auth.bootstrap import ensure_default_admin
from fastapi.testclient import TestClient

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
SAMPLE_ZIP = FIXTURES_DIR / "sample_recording.zip"


@pytest.fixture(scope="session")
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    _ensure_admin_user()
    from app.skill_hub.bootstrap import ensure_skill_hub_startup
    ensure_skill_hub_startup(engine)
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def admin_token(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert r.status_code == 200
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def eng_token(client, admin_token):
    r = client.post(
        "/api/auth/add-user",
        json={"username": "eng_test", "password": "eng123456", "role": "Engineer"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    if r.status_code == 200:
        return r.json()["access_token"]
    r = client.post("/api/auth/login", json={"username": "eng_test", "password": "eng123456"})
    assert r.status_code == 200
    return r.json()["access_token"]


@pytest.fixture()
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture()
def eng_headers(eng_token):
    return {"Authorization": f"Bearer {eng_token}"}


@pytest.fixture()
def default_kb_id(client, auth_headers):
    """全站默认知识库 ID（单库模式）。"""
    r = client.get("/api/knowledge-base/bases/default", headers=auth_headers)
    assert r.status_code == 200, r.text
    return r.json()["id"]


@pytest.fixture()
def kb_id(default_kb_id):
    """兼容旧测试名：指向默认知识库。"""
    return default_kb_id


def _ensure_admin_user():
    ensure_default_admin()
