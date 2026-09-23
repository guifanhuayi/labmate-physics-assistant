from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://labmate:labmate@localhost:5432/labmate"
    session_cookie_name: str = "labmate_session"
    session_hours: int = 24 * 30
    cookie_secure: bool = False
    demo_auth_enabled: bool = False
    demo_student_account: str = "20260001"
    demo_teacher_account: str = "t0001"
    demo_admin_account: str = "admin"
    allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )
    login_attempt_limit: int = 5
    login_lock_minutes: int = 15
    sms_delivery_mode: str = "disabled"
    sms_verification_test_code: str | None = None
    sms_verification_expiry_seconds: int = 600
    sms_verification_resend_seconds: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()
