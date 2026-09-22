from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
import pytest

from app.api import auth as auth_api
from app.auth.service import AuthService
from app.config import Settings
from app.db.models import AuditLog, AuthSession
from app.main import app


def login(client, account="20260001", password="InitialPass2026"):
    return client.post("/api/auth/login", json={"account": account, "password": password})


@pytest.mark.parametrize(
    ("role", "account"),
    [("student", "20260001"), ("teacher", "t0001"), ("admin", "admin")],
)
def test_each_role_can_open_only_its_own_workspace(client, seed_user, role, account) -> None:
    seed_user(role=role, account=account, must_change_password=False)

    response = login(client, account=account)

    assert response.status_code == 200
    assert response.json()["role"] == role
    assert client.get(f"/api/workspaces/{role}").status_code == 200


def test_login_skips_initial_password_change_and_persists_for_thirty_days(client, seed_user) -> None:
    user = seed_user(must_change_password=True)

    response = login(client)

    assert response.status_code == 200
    assert user.password_hash != "InitialPass2026"
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert "max-age=2592000" in cookie
    assert client.get("/api/workspaces/student").status_code == 200


def test_password_change_revokes_other_sessions(client, seed_user) -> None:
    seed_user(must_change_password=True)
    second_client = TestClient(app, headers={"Origin": "http://localhost:5173"})
    try:
        assert login(client).status_code == 200
        assert login(second_client).status_code == 200

        changed = client.post(
            "/api/auth/change-initial-password",
            json={"currentPassword": "InitialPass2026", "newPassword": "NewSecurePass2026"},
        )

        assert changed.status_code == 200
        assert second_client.get("/api/auth/me").status_code == 401
    finally:
        second_client.close()


def test_role_mismatch_is_forbidden_and_audited(client, seed_user, db) -> None:
    seed_user(must_change_password=False)
    assert login(client).status_code == 200

    response = client.get("/api/workspaces/teacher")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"
    db.expire_all()
    audit = db.scalar(select(AuditLog).where(AuditLog.action == "auth.authorization_denied"))
    assert audit is not None
    assert audit.resource_id == "teacher"


def test_logout_revokes_current_session(client, seed_user) -> None:
    seed_user(must_change_password=False)
    assert login(client).status_code == 200

    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/logout").status_code == 204


def test_expired_session_is_rejected(client, seed_user, db) -> None:
    seed_user(must_change_password=False)
    assert login(client).status_code == 200
    session = db.scalar(select(AuthSession))
    session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()

    response = client.get("/api/auth/me")

    assert response.status_code == 401


def test_inactive_account_and_invalid_password_have_stable_codes(client, seed_user) -> None:
    seed_user(account="inactive", status="inactive")
    inactive = login(client, account="inactive")
    invalid = login(client, account="missing", password="wrong")

    assert inactive.status_code == 403
    assert inactive.json()["error"]["code"] == "account_inactive"
    assert invalid.status_code == 401
    assert invalid.json()["error"]["code"] == "invalid_credentials"


def test_fifth_failed_login_triggers_rate_limit(client, seed_user) -> None:
    seed_user()
    for _ in range(5):
        assert login(client, password="wrong").status_code == 401

    response = login(client)

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"


def test_demo_login_accepts_any_credentials_without_rate_limit(client, seed_user, monkeypatch) -> None:
    seed_user(account="20260001")
    monkeypatch.setenv("DEMO_AUTH_ENABLED", "true")
    monkeypatch.setattr(auth_api, "auth_service", AuthService(Settings()))

    for _ in range(7):
        response = login(client, account="任意账号", password="任意密码")
        assert response.status_code == 200
        assert response.json()["role"] == "student"

    assert client.get("/api/workspaces/student").status_code == 200


def test_demo_login_accepts_empty_credentials(client, seed_user, monkeypatch) -> None:
    seed_user(account="20260001")
    monkeypatch.setenv("DEMO_AUTH_ENABLED", "true")
    monkeypatch.setattr(auth_api, "auth_service", AuthService(Settings()))

    response = login(client, account="", password="")

    assert response.status_code == 200
    assert response.json()["role"] == "student"
