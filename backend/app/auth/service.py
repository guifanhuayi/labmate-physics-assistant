from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.auth.errors import AuthError
from app.config import Settings
from app.db.models import AuditLog, AuthSession, ClassMember, PhoneVerification, User


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


def normalize_phone(phone: str) -> str:
    return "".join(character for character in phone if character.isdigit())


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

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value if value.tzinfo else value.replace(tzinfo=UTC)

    def _student_for_enrollment(self, db: Session, name: str, student_number: str) -> User:
        normalized_number = student_number.strip()
        user = db.scalar(
            select(User).where(
                User.role == "student",
                User.student_number == normalized_number,
                User.name == name.strip(),
                User.status == "active",
                User.enrollment_completed.is_(False),
            )
        )
        if not user:
            raise AuthError("enrollment_not_available", "姓名、学号不匹配或账号已完成首次设置。", 404)
        return user

    def request_student_verification(
        self,
        db: Session,
        *,
        name: str,
        student_number: str,
        phone: str,
        client_ip: str | None,
    ) -> int:
        if self.settings.demo_auth_enabled:
            raise AuthError("enrollment_unavailable", "演示模式无需首次设置。", 404)
        if self.settings.sms_delivery_mode != "test" or not self.settings.sms_verification_test_code:
            raise AuthError("sms_unavailable", "短信服务尚未配置，请联系管理员。", 503)
        user = self._student_for_enrollment(db, name, student_number)
        normalized_phone = normalize_phone(phone)
        owner = db.scalar(select(User).where(User.phone_number == normalized_phone))
        if owner and owner.id != user.id:
            raise AuthError("enrollment_not_available", "姓名、学号或手机号无法用于首次设置。", 404)

        latest = db.scalar(
            select(PhoneVerification)
            .where(PhoneVerification.user_id == user.id)
            .order_by(PhoneVerification.created_at.desc())
            .limit(1)
        )
        now = self._now()
        if latest and (now - self._as_utc(latest.created_at)).total_seconds() < self.settings.sms_verification_resend_seconds:
            raise AuthError("verification_too_frequent", "验证码发送过于频繁，请稍后再试。", 429)

        verification = PhoneVerification(
            user_id=user.id,
            phone_number=normalized_phone,
            code_hash=self.hash_password(self.settings.sms_verification_test_code),
            failed_attempts=0,
            created_at=now,
            expires_at=now + timedelta(seconds=self.settings.sms_verification_expiry_seconds),
        )
        db.add(verification)
        self._audit(
            db,
            "auth.student_verification_requested",
            actor_id=user.id,
            resource_id=str(user.id),
            metadata={"ip": client_ip, "phoneLast4": normalized_phone[-4:]},
        )
        db.commit()
        return self.settings.sms_verification_expiry_seconds

    def complete_student_enrollment(
        self,
        db: Session,
        *,
        name: str,
        student_number: str,
        phone: str,
        verification_code: str,
        password: str,
        client_ip: str | None,
    ) -> AuthenticatedSession:
        if self.settings.demo_auth_enabled:
            raise AuthError("enrollment_unavailable", "演示模式无需首次设置。", 404)
        user = self._student_for_enrollment(db, name, student_number)
        normalized_phone = normalize_phone(phone)
        verification = db.scalar(
            select(PhoneVerification)
            .where(
                PhoneVerification.user_id == user.id,
                PhoneVerification.phone_number == normalized_phone,
                PhoneVerification.used_at.is_(None),
            )
            .order_by(PhoneVerification.created_at.desc())
            .limit(1)
        )
        now = self._now()
        if (
            not verification
            or self._as_utc(verification.expires_at) <= now
            or verification.failed_attempts >= 5
        ):
            raise AuthError("invalid_verification_code", "验证码无效或已过期。", 422)
        if not self._verify(verification.code_hash, verification_code):
            verification.failed_attempts += 1
            self._audit(
                db,
                "auth.student_verification_failed",
                actor_id=user.id,
                resource_id=str(user.id),
                metadata={"ip": client_ip},
            )
            db.commit()
            raise AuthError("invalid_verification_code", "验证码无效或已过期。", 422)

        validate_password(password)
        phone_owner = db.scalar(select(User).where(User.phone_number == normalized_phone, User.id != user.id))
        if phone_owner:
            raise AuthError("phone_already_bound", "该手机号已绑定其他账号。", 409)

        user.password_hash = self.hash_password(password)
        user.phone_number = normalized_phone
        user.phone_verified_at = now
        user.enrollment_completed = True
        user.must_change_password = False
        verification.used_at = now
        result = self._create_session(db, user)
        self._audit(
            db,
            "auth.student_enrollment_completed",
            actor_id=user.id,
            resource_id=str(user.id),
            metadata={"ip": client_ip, "phoneLast4": normalized_phone[-4:]},
        )
        db.commit()
        return result

    def _authenticate_demo(self, db: Session, account: str, password: str, client_ip: str | None) -> AuthenticatedSession:
        normalized = normalize_account(account)
        if not normalized or not password:
            raise AuthError("invalid_demo_credentials", "请输入账号和任意非空密码。", 401)
        user = db.scalar(select(User).where(User.account == normalized, User.status == "active"))
        if not user:
            raise AuthError("invalid_demo_credentials", "账号不存在、未导入班级名单或已停用。", 401)
        if user.role == "student" and (
            normalize_account(user.student_number or "") != normalized
            or not db.scalar(select(ClassMember.id).where(ClassMember.user_id == user.id))
        ):
            raise AuthError("invalid_demo_credentials", "账号不存在、未导入班级名单或已停用。", 401)

        result = self._create_session(db, user)
        self._audit(
            db,
            "auth.login_succeeded",
            actor_id=user.id,
            resource_id=normalized,
            metadata={"ip": client_ip, "demo": True},
        )
        db.commit()
        return result

    def authenticate(self, db: Session, account: str, password: str, client_ip: str | None) -> AuthenticatedSession:
        if self.settings.demo_auth_enabled:
            return self._authenticate_demo(db, account, password, client_ip)

        normalized = normalize_account(account)
        normalized_phone = normalize_phone(account)
        user = db.scalar(
            select(User).where(or_(User.account == normalized, User.phone_number == normalized_phone))
        )
        if user and user.role != "student" and self._recent_failures(db, normalized) >= self.settings.login_attempt_limit:
            self._audit(db, "auth.login_rate_limited", resource_id=normalized, metadata={"ip": client_ip})
            db.commit()
            raise AuthError("rate_limited", "登录尝试过多，请 15 分钟后再试。", 429)

        password_ok = self._verify(user.password_hash if user else self._dummy_hash, password)
        if user and user.role == "student" and not user.enrollment_completed:
            password_ok = False
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
