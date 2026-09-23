"""Add student enrollment and verified phone login."""

from alembic import op
import sqlalchemy as sa


revision = "20260923_0004"
down_revision = "20260921_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("phone_number", sa.String(length=32), nullable=True))
    op.add_column("users", sa.Column("phone_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "users",
        sa.Column("enrollment_completed", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.execute(sa.text("UPDATE users SET enrollment_completed = false WHERE role = 'student'"))
    op.create_index("ix_users_phone_number", "users", ["phone_number"], unique=True)
    op.create_table(
        "phone_verifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("phone_number", sa.String(length=32), nullable=False),
        sa.Column("code_hash", sa.Text(), nullable=False),
        sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_phone_verifications_user_id", "phone_verifications", ["user_id"])
    op.create_index("ix_phone_verifications_phone_number", "phone_verifications", ["phone_number"])
    op.create_index("ix_phone_verifications_created_at", "phone_verifications", ["created_at"])
    op.create_index("ix_phone_verifications_expires_at", "phone_verifications", ["expires_at"])


def downgrade() -> None:
    op.drop_table("phone_verifications")
    op.drop_index("ix_users_phone_number", table_name="users")
    op.drop_column("users", "enrollment_completed")
    op.drop_column("users", "phone_verified_at")
    op.drop_column("users", "phone_number")
