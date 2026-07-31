"""
平台横切冒烟：确认主模块在引入 test_manage 后仍可登录与访问核心只读接口。
不依赖外部 LLM/Ollama；失败应视为平台回归。
"""
from __future__ import annotations


class TestPlatformHealth:
    def test_health(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200

    def test_login_admin(self, client):
        r = client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
        assert r.status_code == 200
        assert r.json()["user"]["role"] == "Admin"


class TestAuthGuardsExtended:
    """补齐各业务前缀未登录 401（与 test_unauthorized 互补）。"""

    def test_kb_no_auth(self, client):
        r = client.get("/api/knowledge-base/bases/default")
        assert r.status_code == 401

    def test_tool_hub_no_auth(self, client):
        r = client.get("/api/tool-hub/tools")
        assert r.status_code == 401

    def test_work_daily_no_auth(self, client):
        r = client.get("/api/work-daily")
        assert r.status_code == 401

    def test_test_manage_no_auth(self, client):
        r = client.get("/api/test-manage/week")
        assert r.status_code == 401

    def test_data_cleaning_no_auth(self, client):
        r = client.get("/api/data-cleaning/jobs")
        assert r.status_code in (401, 404, 405)  # 路由名以实际为准，不能是 200


class TestCoreModulesSmoke:
    def test_skills_list(self, client, auth_headers):
        r = client.get("/api/skills", headers=auth_headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_changelog_list(self, client, auth_headers):
        r = client.get("/api/changelog", headers=auth_headers)
        assert r.status_code == 200

    def test_tool_hub_list(self, client, auth_headers):
        r = client.get("/api/tool-hub/tools", headers=auth_headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_knowledge_base_default(self, client, auth_headers, default_kb_id):
        assert default_kb_id
        r = client.get(f"/api/knowledge-base/bases/{default_kb_id}", headers=auth_headers)
        # 有的版本只有 /bases/default；兼容 200 或跳转式接口
        assert r.status_code in (200, 404)
        r = client.get("/api/knowledge-base/bases/default", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["id"] == default_kb_id

    def test_knowledge_base_chat_history_empty_ok(self, client, auth_headers, default_kb_id):
        r = client.get(
            f"/api/knowledge-base/bases/{default_kb_id}/messages",
            headers=auth_headers,
        )
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_work_daily_list(self, client, auth_headers):
        r = client.get("/api/work-daily", headers=auth_headers)
        assert r.status_code == 200

    def test_translate_jobs_list(self, client, auth_headers):
        r = client.get("/api/translate/jobs", headers=auth_headers)
        assert r.status_code == 200

    def test_test_manage_week_and_board(self, client, auth_headers):
        r = client.get("/api/test-manage/week", headers=auth_headers)
        assert r.status_code == 200
        assert "week_key" in r.json()
        r = client.get("/api/test-manage/board", headers=auth_headers)
        assert r.status_code == 200
        assert "tasks" in r.json()

    def test_manager_can_access_board(self, client):
        r = client.post(
            "/api/auth/login",
            json={"username": "manager", "password": "123456"},
        )
        assert r.status_code == 200
        headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
        r = client.get("/api/test-manage/board", headers=headers)
        assert r.status_code == 200

    def test_eng_can_read_skills_and_tools(self, client, eng_headers):
        assert client.get("/api/skills", headers=eng_headers).status_code == 200
        assert client.get("/api/tool-hub/tools", headers=eng_headers).status_code == 200
        assert client.get("/api/knowledge-base/bases/default", headers=eng_headers).status_code == 200
