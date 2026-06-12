import sys
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from app.main_merged import app
from app.core.database import SessionLocal, engine, Base
from app.auth.models import User
from app.auth.service import hash_password
from fastapi.testclient import TestClient

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
SAMPLE_ZIP = FIXTURES_DIR / "sample_recording.zip"


@pytest.fixture(scope="session")
def client():
    Base.metadata.create_all(bind=engine)
    _ensure_admin_user()
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
        "/api/auth/register",
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


def _ensure_admin_user():
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == "admin").first()
        if not user:
            user = User(
                username="admin",
                password_hash=hash_password("admin"),
                role="admin",
            )
            db.add(user)
            db.commit()
    finally:
        db.close()
