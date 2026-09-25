"""Keep deleted assignments and their data for a fixed 30-day recovery period."""

from alembic import op
import sqlalchemy as sa


revision = "20260924_0006"
down_revision = "20260923_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("assignments", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("assignments", sa.Column("purge_after", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_assignments_purge_after", "assignments", ["purge_after"])


def downgrade() -> None:
    op.drop_index("ix_assignments_purge_after", table_name="assignments")
    op.drop_column("assignments", "purge_after")
    op.drop_column("assignments", "deleted_at")
