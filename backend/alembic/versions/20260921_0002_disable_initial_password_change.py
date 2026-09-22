"""Disable mandatory initial password changes for existing accounts."""

from alembic import op
import sqlalchemy as sa


revision = "20260921_0002"
down_revision = "20260917_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("UPDATE users SET must_change_password = false"))
    op.alter_column("users", "must_change_password", server_default=sa.false())


def downgrade() -> None:
    op.alter_column("users", "must_change_password", server_default=sa.true())
