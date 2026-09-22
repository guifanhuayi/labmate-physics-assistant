"""Add classes, roster imports, templates, versions and assignments."""

from alembic import op
import sqlalchemy as sa


revision = "20260921_0003"
down_revision = "20260921_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "classes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("class_code", sa.String(64), nullable=False),
        sa.Column("class_name", sa.String(120), nullable=False),
        sa.Column("semester", sa.String(32), nullable=False),
        sa.Column("teacher_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["teacher_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("class_code", "semester", name="uq_classes_code_semester"),
    )
    op.create_index("ix_classes_class_code", "classes", ["class_code"])
    op.create_index("ix_classes_semester", "classes", ["semester"])
    op.create_index("ix_classes_teacher_id", "classes", ["teacher_id"])
    op.create_table(
        "class_members",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("class_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["class_id"], ["classes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("class_id", "user_id", name="uq_class_members_class_user"),
    )
    op.create_index("ix_class_members_class_id", "class_members", ["class_id"])
    op.create_index("ix_class_members_user_id", "class_members", ["user_id"])
    op.create_table(
        "roster_imports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("class_id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("source_name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="preview"),
        sa.Column("rows_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("errors_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status in ('preview', 'committed')", name="ck_roster_imports_status"),
        sa.ForeignKeyConstraint(["class_id"], ["classes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_roster_imports_class_id", "roster_imports", ["class_id"])
    op.create_index("ix_roster_imports_created_by", "roster_imports", ["created_by"])
    op.create_table(
        "experiment_templates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("owner_teacher_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("draft_schema_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status in ('draft', 'published', 'archived')", name="ck_templates_status"),
        sa.ForeignKeyConstraint(["owner_teacher_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_experiment_templates_owner_teacher_id", "experiment_templates", ["owner_teacher_id"])
    op.create_index("ix_experiment_templates_status", "experiment_templates", ["status"])
    op.create_table(
        "template_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("template_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("schema_json", sa.JSON(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["template_id"], ["experiment_templates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("template_id", "version_number", name="uq_template_versions_number"),
    )
    op.create_index("ix_template_versions_template_id", "template_versions", ["template_id"])
    op.create_table(
        "assignments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("template_version_id", sa.Uuid(), nullable=False),
        sa.Column("class_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status in ('draft', 'open', 'closed')", name="ck_assignments_status"),
        sa.ForeignKeyConstraint(["class_id"], ["classes.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["template_version_id"], ["template_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_assignments_template_version_id", "assignments", ["template_version_id"])
    op.create_index("ix_assignments_class_id", "assignments", ["class_id"])
    op.create_index("ix_assignments_status", "assignments", ["status"])
    op.create_index("ix_assignments_created_by", "assignments", ["created_by"])


def downgrade() -> None:
    op.drop_table("assignments")
    op.drop_table("template_versions")
    op.drop_table("experiment_templates")
    op.drop_table("roster_imports")
    op.drop_table("class_members")
    op.drop_table("classes")
