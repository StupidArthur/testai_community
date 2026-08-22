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

    def test_admin_can_change_user_password(self, client, admin_token, eng_token):
        """用户管理「更改密码」：Admin 可为任意用户设置新密码。"""
        users = client.get("/api/auth/user-list", headers={"Authorization": f"Bearer {admin_token}"}).json()
        eng = next(u for u in users if u["username"] == "eng_test")
        r = client.post(
            f"/api/auth/{eng['id']}/reset-password",
            json={"new_password": "changed_by_admin"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 200
        assert r.json()["message"] == "密码已更改"
        assert client.post("/api/auth/login", json={"username": "eng_test", "password": "changed_by_admin"}).status_code == 200
        # 改回，避免影响其它用例
        client.post(
            f"/api/auth/{eng['id']}/reset-password",
            json={"new_password": "eng123456"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )

    def test_admin_can_change_admin_password(self, client, admin_token):
        """原先会 403「不能重置其他管理员的密码」，含改自己也会被拦。"""
        from app.auth.service import hash_password
        from app.platform.database import SessionLocal
        from app.auth.models import User

        users = client.get("/api/auth/user-list", headers={"Authorization": f"Bearer {admin_token}"}).json()
        admin = next(u for u in users if u["username"] == "admin")
        r = client.post(
            f"/api/auth/{admin['id']}/reset-password",
            json={"new_password": "admin12"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 200, r.text
        assert client.post("/api/auth/login", json={"username": "admin", "password": "admin12"}).status_code == 200
        # 恢复默认口令，避免影响同 session 其它用例（默认 admin 仅 5 位，接口要求 ≥6）
        db = SessionLocal()
        try:
            row = db.query(User).filter(User.id == admin["id"]).first()
            row.password_hash = hash_password("admin")
            db.commit()
        finally:
            db.close()


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
