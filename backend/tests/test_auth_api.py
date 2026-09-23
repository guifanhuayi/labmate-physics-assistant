from datetime import UTC, datetime, timedelta

from sqlalchemy import select
import pytest

from app.api import auth as auth_api
from app.auth.service import AuthService
from app.config import Settings
from app.db.models import AuditLog, AuthSession


def login(client, account="20260001", password="SecurePass2026"):
    return client.post("/api/auth/login", json={"account": account, "password": password})


@pytest.mark.parametrize(
    ("role", "account"),
    [("student", "20260001"), ("teacher", "t0001"), ("admin", "admin")],
)
def test_each_enrolled_role_can_open_only_its_own_workspace(client, seed_user, role, account) -> None:
    seed_user(role=role, account=account, password="SecurePass2026", enrollment_completed=True)
    response = login(client, account=account)
    assert response.status_code == 200
    assert response.json()["role"] == role
    assert client.get(f"/api/workspaces/{role}").status_code == 200


def test_student_enrolls_without_activation_code_and_can_login_by_phone(client, seed_user, monkeypatch) -> None:
    user = seed_user(
        account="20260001",
        password="UnusableRandomPass2026",
        name="测试学生",
        enrollment_completed=False,
    )
    monkeypatch.setattr(
        auth_api,
        "auth_service",
        AuthService(Settings(sms_delivery_mode="test", sms_verification_test_code="246810")),
    )
    requested = client.post(
        "/api/auth/student-enrollment/sms",
        json={"name": "测试学生", "studentNumber": "20260001", "phone": "13800000001"},
    )
    assert requested.status_code == 202
    assert requested.json() == {"expiresInSeconds": 600}

    completed = client.post(
        "/api/auth/student-enrollment/complete",
        json={
            "name": "测试学生",
            "studentNumber": "20260001",
            "phone": "13800000001",
            "verificationCode": "246810",
            "password": "NewSecurePass2026",
        },
    )
    assert completed.status_code == 200
    assert completed.json()["enrollmentCompleted"] is True
    assert completed.json()["phoneMasked"] == "138****0001"
    assert "httponly" in completed.headers["set-cookie"].lower()
    assert client.post("/api/auth/logout").status_code == 204
    assert login(client, account="13800000001", password="NewSecurePass2026").status_code == 200
    assert user.password_hash != "NewSecurePass2026"


def test_student_enrollment_rejects_wrong_identity_and_reuse(client, seed_user, monkeypatch) -> None:
    seed_user(account="20260001", name="测试学生", enrollment_completed=False)
    monkeypatch.setattr(
        auth_api,
        "auth_service",
        AuthService(Settings(sms_delivery_mode="test", sms_verification_test_code="246810")),
    )
    wrong = client.post(
        "/api/auth/student-enrollment/sms",
        json={"name": "错误姓名", "studentNumber": "20260001", "phone": "13800000001"},
    )
    assert wrong.status_code == 404
    assert wrong.json()["error"]["code"] == "enrollment_not_available"

    assert client.post(
        "/api/auth/student-enrollment/sms",
        json={"name": "测试学生", "studentNumber": "20260001", "phone": "13800000001"},
    ).status_code == 202
    payload = {
        "name": "测试学生",
        "studentNumber": "20260001",
        "phone": "13800000001",
        "verificationCode": "246810",
        "password": "NewSecurePass2026",
    }
    assert client.post("/api/auth/student-enrollment/complete", json=payload).status_code == 200
    payload["password"] = "AnotherPass2026"
    assert client.post("/api/auth/student-enrollment/complete", json=payload).status_code == 404


def test_login_persists_for_thirty_days(client, seed_user) -> None:
    seed_user(password="SecurePass2026", enrollment_completed=True)
    response = login(client)
    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert "max-age=2592000" in cookie
    assert client.get("/api/workspaces/student").status_code == 200


def test_student_is_not_locked_after_repeated_wrong_passwords(client, seed_user) -> None:
    seed_user(password="SecurePass2026", enrollment_completed=True)
    for _ in range(7):
        assert login(client, password="wrong").status_code == 401
    assert login(client).status_code == 200


def test_teacher_still_has_account_level_brute_force_protection(client, seed_user) -> None:
    seed_user(role="teacher", account="t0001", password="SecurePass2026", enrollment_completed=True)
    for _ in range(5):
        assert login(client, account="t0001", password="wrong").status_code == 401
    response = login(client, account="t0001")
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"


def test_role_mismatch_is_forbidden_and_audited(client, seed_user, db) -> None:
    seed_user(password="SecurePass2026", enrollment_completed=True)
    assert login(client).status_code == 200
    response = client.get("/api/workspaces/teacher")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"
    db.expire_all()
    audit = db.scalar(select(AuditLog).where(AuditLog.action == "auth.authorization_denied"))
    assert audit is not None
    assert audit.resource_id == "teacher"


def test_logout_revokes_current_session(client, seed_user) -> None:
    seed_user(password="SecurePass2026", enrollment_completed=True)
    assert login(client).status_code == 200
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/logout").status_code == 204


def test_expired_session_is_rejected(client, seed_user, db) -> None:
    seed_user(password="SecurePass2026", enrollment_completed=True)
    assert login(client).status_code == 200
    session = db.scalar(select(AuthSession))
    session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    assert client.get("/api/auth/me").status_code == 401


def test_inactive_account_and_invalid_password_have_stable_codes(client, seed_user) -> None:
    seed_user(account="inactive", status="inactive", password="SecurePass2026", enrollment_completed=True)
    inactive = login(client, account="inactive")
    invalid = login(client, account="missing", password="wrong")
    assert inactive.status_code == 403
    assert inactive.json()["error"]["code"] == "account_inactive"
    assert invalid.status_code == 401
    assert invalid.json()["error"]["code"] == "invalid_credentials"


def test_demo_login_uses_existing_account_and_any_numeric_password(client, seed_user, monkeypatch) -> None:
    seed_user(account="20260001", enrollment_completed=False)
    seed_user(account="20269999", enrollment_completed=False)
    seed_user(role="teacher", account="t0001", enrollment_completed=True)
    seed_user(role="admin", account="admin", enrollment_completed=True)
    demo_settings = Settings(demo_auth_enabled=True)
    monkeypatch.setattr(auth_api, "settings", demo_settings)
    monkeypatch.setattr(auth_api, "auth_service", AuthService(demo_settings))

    mode = client.get("/api/auth/mode")
    assert mode.status_code == 200
    assert mode.json()["demoEnabled"] is True
    assert mode.json()["demoAccounts"] == {"student": "20260001", "teacher": "t0001", "admin": "admin"}

    for account, role in (("20260001", "student"), ("20269999", "student"), ("t0001", "teacher"), ("admin", "admin")):
        response = client.post("/api/auth/login", json={"account": account, "password": "123"})
        assert response.status_code == 200
        assert response.json()["role"] == role
        assert client.get(f"/api/workspaces/{role}").status_code == 200

    for account, password in (("", "123"), ("missing", "123"), ("20260001", "letters"), ("20260001", "")):
        response = client.post("/api/auth/login", json={"account": account, "password": password})
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "invalid_demo_credentials"

    assert client.post(
        "/api/auth/student-enrollment/sms",
        json={"name": "测试student", "studentNumber": "20260001", "phone": "13800000001"},
    ).status_code == 404
