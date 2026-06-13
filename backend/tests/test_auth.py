"""认证全流程测试：登录、添加用户、JWT、ticket、权限。"""


class TestLogin:
    def test_admin_login(self, client):
        r = client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
        assert r.status_code == 200
        data = r.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["user"]["username"] == "admin"
        assert data["user"]["role"] == "Admin"

    def test_wrong_password(self, client):
        r = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
        assert r.status_code == 401

    def test_nonexistent_user(self, client):
        r = client.post("/api/auth/login", json={"username": "nobody", "password": "x"})
        assert r.status_code == 401


class TestAddUser:
    def test_admin_can_create_eng(self, client, admin_token):
        import uuid
        uname = f"eng_{uuid.uuid4().hex[:8]}"
        r = client.post(
            "/api/auth/add-user",
            json={"username": uname, "password": "eng123456", "role": "Engineer"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 200
        assert r.json()["user"]["role"] == "Engineer"

    def test_duplicate_username(self, client, admin_token):
        r = client.post(
            "/api/auth/add-user",
            json={"username": "admin", "password": "admin123456", "role": "Engineer"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 400

    def test_eng_cannot_create_user(self, client, eng_token):
        r = client.post(
            "/api/auth/add-user",
            json={"username": "eng_forbidden", "password": "eng123456", "role": "Engineer"},
            headers={"Authorization": f"Bearer {eng_token}"},
        )
        assert r.status_code == 403

    def test_add_user_requires_admin(self, client):
        r = client.post(
            "/api/auth/add-user",
            json={"username": "noauth_user", "password": "eng123456", "role": "Engineer"},
        )
        assert r.status_code == 401

    def test_missing_bearer_returns_401_not_403(self, client):
        r = client.get("/api/auth/current-user")
        assert r.status_code == 401


class TestUserManagement:
    def test_list_users_admin(self, client, admin_token):
        r = client.get("/api/auth/user-list", headers={"Authorization": f"Bearer {admin_token}"})
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_list_users_eng_forbidden(self, client, eng_token):
        r = client.get("/api/auth/user-list", headers={"Authorization": f"Bearer {eng_token}"})
        assert r.status_code == 403

    def test_current_user(self, client, admin_token):
        r = client.get("/api/auth/current-user", headers={"Authorization": f"Bearer {admin_token}"})
        assert r.status_code == 200
        assert r.json()["username"] == "admin"

    def test_change_password(self, client, eng_token):
        r = client.put(
            "/api/auth/password",
            json={"old_password": "eng123456", "new_password": "neweng123456"},
            headers={"Authorization": f"Bearer {eng_token}"},
        )
        assert r.status_code == 200

        r2 = client.post("/api/auth/login", json={"username": "eng_test", "password": "neweng123456"})
        assert r2.status_code == 200

        r3 = client.put(
            "/api/auth/password",
            json={"old_password": "neweng123456", "new_password": "eng123456"},
            headers={"Authorization": f"Bearer {eng_token}"},
        )
        assert r3.status_code == 200


class TestTicketMechanism:
    def test_create_ticket(self, client, admin_token):
        r = client.post(
            "/api/translate/ticket",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert "ticket" in data
        assert data["expires_in"] == 30

    def test_ticket_single_use(self, client, admin_token):
        r = client.post(
            "/api/translate/ticket",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        ticket = r.json()["ticket"]

        r1 = client.get(f"/api/translate/prompts?ticket={ticket}")
        assert r1.status_code == 200

        r2 = client.get(f"/api/translate/prompts?ticket={ticket}")
        assert r2.status_code == 401

    def test_invalid_ticket(self, client):
        r = client.get("/api/translate/prompts?ticket=fake_ticket_12345")
        assert r.status_code == 401

    def test_invalid_jwt(self, client):
        r = client.get(
            "/api/translate/jobs",
            headers={"Authorization": "Bearer invalid.jwt.token"},
        )
        assert r.status_code == 401

    def test_query_jwt_deprecated(self, client, admin_token):
        """query token=JWT 已废弃，仅接受 ticket。"""
        r = client.get(f"/api/translate/prompts?token={admin_token}")
        assert r.status_code == 401
