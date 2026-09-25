"""Add stage-four student drafts and assignment-scoped group data."""

from alembic import op
import sqlalchemy as sa


revision = "20260923_0005"
down_revision = "20260923_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("assignments", sa.Column("group_sharing_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table(
        "experiment_groups",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("assignment_id", sa.Uuid(), sa.ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("assignment_id", "name", name="uq_experiment_groups_name"),
    )
    op.create_index("ix_experiment_groups_assignment_id", "experiment_groups", ["assignment_id"])
    op.create_table(
        "group_members",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("assignment_id", sa.Uuid(), sa.ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("group_id", sa.Uuid(), sa.ForeignKey("experiment_groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("assignment_id", "user_id", name="uq_group_members_assignment_user"),
        sa.UniqueConstraint("group_id", "user_id", name="uq_group_members_group_user"),
    )
    for column in ("assignment_id", "group_id", "user_id"):
        op.create_index(f"ix_group_members_{column}", "group_members", [column])
    op.create_table(
        "submission_drafts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("assignment_id", sa.Uuid(), sa.ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("student_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("values_json", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("assignment_id", "student_id", name="uq_submission_drafts_assignment_student"),
    )
    op.create_index("ix_submission_drafts_assignment_id", "submission_drafts", ["assignment_id"])
    op.create_index("ix_submission_drafts_student_id", "submission_drafts", ["student_id"])
    op.create_table(
        "draft_mutations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("draft_id", sa.Uuid(), sa.ForeignKey("submission_drafts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("request_id", sa.String(36), nullable=False, unique=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("draft_id", "version", name="uq_draft_mutations_version"),
    )
    op.create_index("ix_draft_mutations_draft_id", "draft_mutations", ["draft_id"])
    op.create_table(
        "shared_datasets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("assignment_id", sa.Uuid(), sa.ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("group_id", sa.Uuid(), sa.ForeignKey("experiment_groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("values_json", sa.JSON(), nullable=False),
        sa.Column("sources_json", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("group_id", name="uq_shared_datasets_group"),
    )
    op.create_index("ix_shared_datasets_assignment_id", "shared_datasets", ["assignment_id"])
    op.create_index("ix_shared_datasets_group_id", "shared_datasets", ["group_id"])
    op.create_table(
        "shared_data_revisions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("dataset_id", sa.Uuid(), sa.ForeignKey("shared_datasets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("request_id", sa.String(36), nullable=False, unique=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("changes_json", sa.JSON(), nullable=False),
        sa.Column("edited_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("dataset_id", "version", name="uq_shared_data_revisions_version"),
    )
    for column in ("dataset_id", "edited_by"):
        op.create_index(f"ix_shared_data_revisions_{column}", "shared_data_revisions", [column])


def downgrade() -> None:
    op.drop_table("shared_data_revisions")
    op.drop_table("shared_datasets")
    op.drop_table("draft_mutations")
    op.drop_table("submission_drafts")
    op.drop_table("group_members")
    op.drop_table("experiment_groups")
    op.drop_column("assignments", "group_sharing_enabled")
