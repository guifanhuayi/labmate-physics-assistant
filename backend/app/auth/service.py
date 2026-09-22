from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.auth.errors import AuthError
from app.config import Settings
from app.db.models import AuditLog, AuthSession, User


@dataclass(frozen=True)
class AuthenticatedSession:
    user: User
    session: AuthSession
    token: str


@dataclass(frozen=True)
class CurrentSession:
    user: User
    session: AuthSession


def normalize_account(account: str) -> str:
    return account.strip().casefold()


def validate_password(password: str) -> None:
    if len(password) < 12 or not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        raise AuthError("weak_password", "新密码至少 12 位，并同时包含字母和数字。", 422)


class AuthService:
    """Owns password verification, rate limiting, sessions, rotation and audit."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.passwords = PasswordHasher()
        self._dummy_hash = self.passwords.hash("LabMate-dummy-password-2026")

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def hash_password(self, password: str) -> str:
        return self.passwords.hash(password)

    def _verify(self, stored_hash: str, password: str) -> bool:
        try:
            return self.passwords.verify(stored_hash, password)
        except (InvalidHashError, VerificationError, VerifyMismatchError):
            return False

    def _audit(
        self,
        db: Session,
        action: str,
        *,
        actor_id=None,
        resource_type: str = "auth",
        resource_id: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        db.add(
            AuditLog(
                actor_id=actor_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                metadata_json=metadata or {},
                created_at=self._now(),
            )
        )

    def _recent_failures(self, db: Session, account: str) -> int:
        since = self._now() - timedelta(minutes=self.settings.login_lock_minutes)
        last_success = db.scalar(
            select(func.max(AuditLog.created_at)).where(
                AuditLog.action == "auth.login_succeeded",
                AuditLog.resource_id == account,
            )
        )
        if last_success and last_success.tzinfo is None:
            last_success = last_success.replace(tzinfo=UTC)
        if last_success and last_success > since:
            since = last_success
        statement = select(func.count(AuditLog.id)).where(
            AuditLog.action == "auth.login_failed",
            AuditLog.resource_id == account,
            AuditLog.created_at >= since,
        )
        return int(db.scalar(statement) or 0)

    def _create_session(self, db: Session, user: User) -> AuthenticatedSession:
        now = self._now()
        token = secrets.token_urlsafe(32)
        session = AuthSession(
            user_id=user.id,
            token_hash=self._token_hash(token),
            created_at=now,
            expires_at=now + timedelta(hours=self.settings.session_hours),
        )
        db.add(session)
        db.flush()
        return AuthenticatedSession(user=user, session=session, token=token)

    def _authenticate_demo(self, db: Session, account: str, client_ip: str | None) -> AuthenticatedSession:
        normalized = normalize_account(account)
        known_accounts = {
            normalize_account(self.settings.demo_admin_account),
            normalize_account(self.settings.demo_teacher_account),
            normalize_account(self.settings.demo_student_account),
        }
        selected_account = normalized if normalized in known_accounts else normalize_account(self.settings.demo_student_account)
        user = db.scalar(select(User).where(User.account == selected_account, User.status == "active"))
        if not user:
            raise AuthError("demo_account_unavailable", "演示账号尚未初始化。", 503)

        result = self._create_session(db, user)
        self._audit(
            db,
            "auth.login_succeeded",
            actor_id=user.id,
            resource_id=normalized,
            metadata={"ip": client_ip, "demo": True, "mappedAccount": selected_account},
        )
        db.commit()
        return result

    def authenticate(self, db: Session, account: str, password: str, client_ip: str | None) -> AuthenticatedSession:
        if self.settings.demo_auth_enabled:
            return self._authenticate_demo(db, account, client_ip)

        normalized = normalize_account(account)
        if self._recent_failures(db, normalized) >= self.settings.login_attempt_limit:
            self._audit(db, "auth.login_rate_limited", resource_id=normalized, metadata={"ip": client_ip})
            db.commit()
            raise AuthError("rate_limited", "登录尝试过多，请 15 分钟后再试。", 429)

        user = db.scalar(select(User).where(User.account == normalized))
        password_ok = self._verify(user.password_hash if user else self._dummy_hash, password)
        if not user or not password_ok:
            self._audit(db, "auth.login_failed", resource_id=normalized, metadata={"ip": client_ip})
            db.commit()
            raise AuthError("invalid_credentials", "账号或密码不正确。", 401)

        if user.status != "active":
            self._audit(db, "auth.login_inactive", actor_id=user.id, resource_id=normalized, metadata={"ip": client_ip})
            db.commit()
            raise AuthError("account_inactive", "账号已停用，请联系管理员。", 403)

        result = self._create_session(db, user)
        self._audit(db, "auth.login_succeeded", actor_id=user.id, resource_id=normalized, metadata={"ip": client_ip})
        db.commit()
        return result

    def current(self, db: Session, token: str | None) -> CurrentSession:
        if not token:
            raise AuthError("unauthenticated", "请先登录。", 401)
        token_hash = self._token_hash(token)
        statement = select(AuthSession).where(
            AuthSession.token_hash == token_hash,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > self._now(),
        )
        session = db.scalar(statement)
        if not session:
            raise AuthError("unauthenticated", "登录状态已失效，请重新登录。", 401)
        user = db.get(User, session.user_id)
        if not user or user.status != "active":
            raise AuthError("unauthenticated", "登录状态已失效，请重新登录。", 401)
        return CurrentSession(user=user, session=session)

    def change_initial_password(
        self,
        db: Session,
        current: CurrentSession,
        current_password: str,
        new_password: str,
    ) -> AuthenticatedSession:
        if not current.user.must_change_password:
            raise AuthError("password_already_changed", "初始密码已经修改。", 409)
        if not self._verify(current.user.password_hash, current_password):
            raise AuthError("invalid_credentials", "当前密码不正确。", 401)
        validate_password(new_password)
        if self._verify(current.user.password_hash, new_password):
            raise AuthError("password_reused", "新密码不能与初始密码相同。", 422)

        now = self._now()
        current.user.password_hash = self.hash_password(new_password)
        current.user.must_change_password = False
        db.execute(
            update(AuthSession)
            .where(AuthSession.user_id == current.user.id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        result = self._create_session(db, current.user)
        self._audit(db, "auth.password_changed", actor_id=current.user.id, resource_id=str(current.user.id))
        db.commit()
        return result

    def logout(self, db: Session, current: CurrentSession | None) -> None:
        if current:
            current.session.revoked_at = self._now()
            self._audit(db, "auth.logout", actor_id=current.user.id, resource_id=str(current.session.id))
            db.commit()

    def audit_denied(self, db: Session, user: User, role: str) -> None:
        self._audit(
            db,
            "auth.authorization_denied",
            actor_id=user.id,
            resource_type="workspace",
            resource_id=role,
        )
        db.commit()
