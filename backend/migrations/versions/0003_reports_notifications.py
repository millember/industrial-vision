"""Atomic reports, open issues, internal notifications and replay responses."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003"
down_revision = "0002"


def upgrade():
    op.create_table("issues",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("equipment_id", sa.Integer, sa.ForeignKey("equipment.id"), nullable=False),
        sa.Column("workshop_id", sa.Integer, sa.ForeignKey("workshops.id"), nullable=False),
        sa.Column("defect_type_id", sa.Integer, sa.ForeignKey("defect_types.id"), nullable=False),
        sa.Column("analysis_source", sa.String(8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("analysis_source IN ('MOCK', 'MODEL')", name="ck_issue_source"))
    op.create_index("uq_open_issue", "issues", ["equipment_id", "workshop_id", "defect_type_id", "analysis_source"],
                    unique=True, postgresql_where=sa.text("closed_at IS NULL"))
    op.create_table("reports",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("inspection_id", sa.Integer, sa.ForeignKey("inspections.id"), nullable=False),
        sa.Column("issue_id", sa.Integer, sa.ForeignKey("issues.id"), nullable=False),
        sa.Column("author_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("workshop_id", sa.Integer, sa.ForeignKey("workshops.id"), nullable=False),
        sa.Column("equipment_id", sa.Integer, sa.ForeignKey("equipment.id"), nullable=False),
        sa.Column("comment", sa.String(2000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("body", JSONB, nullable=False))
    op.create_index("ix_reports_inspection_id", "reports", ["inspection_id"])
    op.create_table("report_requests",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("author_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("inspection_id", sa.Integer, sa.ForeignKey("inspections.id"), nullable=False),
        sa.Column("key", sa.String(36), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("response_status", sa.Integer, nullable=False),
        sa.Column("body", JSONB, nullable=False),
        sa.UniqueConstraint("author_id", "inspection_id", "key", name="uq_report_request"))
    op.create_table("notifications",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("report_id", sa.Integer, sa.ForeignKey("reports.id"), nullable=False),
        sa.Column("issue_id", sa.Integer, sa.ForeignKey("issues.id"), nullable=False),
        sa.Column("recipient_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("workshop_id", sa.Integer, sa.ForeignKey("workshops.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("is_read", sa.Boolean, nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("analysis_source", sa.String(8), nullable=False),
        sa.UniqueConstraint("issue_id", "recipient_id", name="uq_notification_issue_recipient"))
    op.create_index("ix_notifications_recipient_created", "notifications", ["recipient_id", sa.text("created_at DESC"), sa.text("id DESC")])


def downgrade():
    raise RuntimeError("Data-destructive downgrade requires an explicit recovery plan")
