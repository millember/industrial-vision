"""Append-only engineering reviews and explicit issue closure."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004"
down_revision = "0003"


def upgrade():
    op.create_table("reviews",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("inspection_id", sa.Integer, sa.ForeignKey("inspections.id"), nullable=False),
        sa.Column("author_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("workshop_id", sa.Integer, sa.ForeignKey("workshops.id"), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False), sa.Column("status", sa.String(16), nullable=False),
        sa.Column("comment", sa.String(2000), nullable=False),
        sa.Column("previous_review_id", sa.Integer, sa.ForeignKey("reviews.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.clock_timestamp(), nullable=False),
        sa.Column("body", JSONB, nullable=False),
        sa.CheckConstraint("(decision = 'CONFIRMED' AND status IN ('OK','WARNING','CRITICAL')) OR (decision = 'REJECTED' AND status = 'UNKNOWN')", name="ck_review_decision"))
    op.create_index("ix_reviews_inspection_id", "reviews", ["inspection_id", sa.text("id DESC")])
    op.create_index("uq_review_first", "reviews", ["inspection_id"], unique=True, postgresql_where=sa.text("previous_review_id IS NULL"))
    op.create_index("uq_review_successor", "reviews", ["previous_review_id"], unique=True, postgresql_where=sa.text("previous_review_id IS NOT NULL"))
    op.add_column("issues", sa.Column("closed_by", sa.Integer, sa.ForeignKey("users.id")))
    op.add_column("issues", sa.Column("close_review_id", sa.Integer, sa.ForeignKey("reviews.id")))
    op.add_column("issues", sa.Column("close_reason", sa.Text))
    op.add_column("issues", sa.Column("resolution", sa.String(16)))
    op.create_table("workflow_requests",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("author_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.String(16), nullable=False), sa.Column("target_id", sa.Integer, nullable=False),
        sa.Column("key", sa.String(36), nullable=False), sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("response_status", sa.Integer, nullable=False), sa.Column("body", JSONB, nullable=False),
        sa.UniqueConstraint("author_id", "action", "target_id", "key", name="uq_workflow_request"),
        sa.CheckConstraint("action IN ('review', 'close')", name="ck_workflow_action"))


def downgrade():
    raise RuntimeError("Data-destructive downgrade requires an explicit recovery plan")
