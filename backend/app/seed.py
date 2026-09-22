from datetime import UTC, datetime
import os

from sqlalchemy import select

from app.api.auth import auth_service
from app.db.models import User
from app.db.session import SessionLocal


SEEDS = (
    ("student", "LABMATE_SEED_STUDENT_ACCOUNT", "20260001", "LABMATE_SEED_STUDENT_NAME", "测试学生", "LABMATE_SEED_STUDENT_PASSWORD"),
    ("teacher", "LABMATE_SEED_TEACHER_ACCOUNT", "t0001", "LABMATE_SEED_TEACHER_NAME", "测试教师", "LABMATE_SEED_TEACHER_PASSWORD"),
    ("admin", "LABMATE_SEED_ADMIN_ACCOUNT", "admin", "LABMATE_SEED_ADMIN_NAME", "测试管理员", "LABMATE_SEED_ADMIN_PASSWORD"),
)


def main() -> None:
    missing = [password_key for *_, password_key in SEEDS if not os.getenv(password_key)]
    if missing:
        raise SystemExit("缺少种子密码环境变量：" + ", ".join(missing))

    with SessionLocal() as db:
        for role, account_key, default_account, name_key, default_name, password_key in SEEDS:
            account = os.getenv(account_key, default_account).strip().casefold()
            if db.scalar(select(User).where(User.account == account)):
                print(f"保留已有账号：{account}")
                continue
            user = User(
                account=account,
                password_hash=auth_service.hash_password(os.environ[password_key]),
                name=os.getenv(name_key, default_name),
                student_number=account if role == "student" else None,
                employee_number=account if role == "teacher" else None,
                role=role,
                status="active",
                must_change_password=False,
                created_at=datetime.now(UTC),
            )
            db.add(user)
            print(f"创建 {role} 账号：{account}")
        db.commit()


if __name__ == "__main__":
    main()
