from datetime import UTC, datetime
import os

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker


TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://labmate:labmate@localhost:5432/labmate_test",
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["COOKIE_SECURE"] = "false"

from app.api.auth import auth_service  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.models import User  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402


IS_SQLITE = TEST_DATABASE_URL.startswith("sqlite")
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False} if IS_SQLITE else {})
TestSession = sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture(scope="session")
def migrated_database() -> None:
    if IS_SQLITE:
        Base.metadata.create_all(engine)
        return
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.upgrade(config, "head")


@pytest.fixture
def clean_database(migrated_database) -> None:
    if IS_SQLITE:
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        return
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE audit_logs, auth_sessions, users RESTART IDENTITY CASCADE"))


@pytest.fixture
def db() -> Session:
    with TestSession() as session:
        yield session


@pytest.fixture
def seed_user(db: Session):
    def create(role: str = "student", account: str | None = None, password: str = "InitialPass2026", **values) -> User:
        selected_account = account or {"student": "20260001", "teacher": "t0001", "admin": "admin"}[role]
        user = User(
            account=selected_account,
            password_hash=auth_service.hash_password(password),
            name=values.pop("name", f"测试{role}"),
            student_number=selected_account if role == "student" else None,
            employee_number=selected_account if role == "teacher" else None,
            role=role,
            status=values.pop("status", "active"),
            must_change_password=values.pop("must_change_password", False),
            created_at=datetime.now(UTC),
            **values,
        )
        db.add(user)
        db.commit()
        return user

    return create


@pytest.fixture
def client(clean_database) -> TestClient:
    def override_db():
        with TestSession() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    with TestClient(app, headers={"Origin": "http://localhost:5173"}) as test_client:
        yield test_client
    app.dependency_overrides.clear()
