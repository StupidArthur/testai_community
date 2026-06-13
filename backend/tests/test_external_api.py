"""external_api 模块 API 测试。"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.platform.database import SessionLocal
from app.external_api.models import ServiceAccount, api_key_fingerprint, hash_api_key


TEST_API_KEY = "test-external-api-key-for-pytest-only"


@pytest.fixture(scope="session")
def external_api_headers(client):
    """写入测试用 ServiceAccount，返回 X-API-Key 请求头。"""
    db = SessionLocal()
    try:
        fp = api_key_fingerprint(TEST_API_KEY)
        existing = db.query(ServiceAccount).filter(ServiceAccount.token_fingerprint == fp).first()
        if not existing:
            db.add(
                ServiceAccount(
                    token_hash=hash_api_key(TEST_API_KEY),
                    token_fingerprint=fp,
                    name="pytest-external",
                )
            )
            db.commit()
    finally:
        db.close()
    return {"X-API-Key": TEST_API_KEY}


@pytest.fixture()
def skill_name(client, auth_headers):
    """供 external_api 调用的 Skill。"""
    name = f"ext_skill_{uuid.uuid4().hex[:8]}"
    r = client.post(
        "/api/skills",
        json={"name": name, "display_name": "External API 测试", "definition": ""},
        headers=auth_headers,
    )
    assert r.status_code == 200
    return name


class TestExternalApiAuth:
    def test_no_api_key(self, client, skill_name):
        r = client.get(f"/api/v1/external/skills/{skill_name}")
        assert r.status_code == 422

    def test_invalid_api_key(self, client, skill_name):
        r = client.get(
            f"/api/v1/external/skills/{skill_name}",
            headers={"X-API-Key": "invalid-key"},
        )
        assert r.status_code == 401


class TestExternalApiSkills:
    def test_get_skill(self, client, external_api_headers, skill_name):
        r = client.get(
            f"/api/v1/external/skills/{skill_name}",
            headers=external_api_headers,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["name"] == skill_name
        assert "payload" in body
        assert "fields" in body

    def test_get_nonexistent_skill(self, client, external_api_headers):
        r = client.get(
            "/api/v1/external/skills/nonexistent_skill_xyz",
            headers=external_api_headers,
        )
        assert r.status_code == 404


class TestExternalApiTasks:
    @patch("app.external_api.service.chat", new_callable=AsyncMock)
    def test_execute_async_and_poll(self, mock_chat, client, external_api_headers, skill_name):
        mock_chat.return_value = "mock llm result"

        r = client.post(
            f"/api/v1/external/skills/{skill_name}/execute-async",
            json={"user_input": "hello"},
            headers=external_api_headers,
        )
        assert r.status_code == 202
        task_id = r.json()["task_id"]

        r2 = client.get(
            f"/api/v1/external/tasks/{task_id}",
            headers=external_api_headers,
        )
        assert r2.status_code == 200
        assert r2.json()["task_id"] == task_id
        assert r2.json()["status"] in ("pending", "processing", "completed", "failed")

    def test_get_nonexistent_task(self, client, external_api_headers):
        r = client.get(
            "/api/v1/external/tasks/nonexistent-task-id",
            headers=external_api_headers,
        )
        assert r.status_code == 404
