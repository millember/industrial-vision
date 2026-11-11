"""Persistent single-photo inspections and idempotency."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002"
down_revision = "0001"


def upgrade():
    op.create_table(
        "inspections",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("equipment_id", sa.Integer, sa.ForeignKey("equipment.id"), nullable=False),
        sa.Column("workshop_id", sa.Integer, sa.ForeignKey("workshops.id"), nullable=False),
        sa.Column("author_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("idempotency_key", sa.String(36), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("processing_status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("photo_key", sa.String(32), unique=True, nullable=False),
        sa.Column("storage_backend", sa.String(16), nullable=False),
        sa.Column("media_type", sa.String(32)),
        sa.Column("checksum", sa.String(64)),
        sa.Column("result", JSONB(none_as_null=True)),
        sa.Column("error", JSONB(none_as_null=True)),
        sa.Column("response_status", sa.Integer),
        sa.Column("cleanup_pending", sa.Boolean, nullable=False),
        sa.UniqueConstraint("author_id", "idempotency_key", name="uq_inspection_author_key"),
        sa.CheckConstraint("processing_status IN ('PROCESSING', 'COMPLETED', 'FAILED')", name="ck_inspection_processing"),
        sa.CheckConstraint("source IN ('CAMERA', 'GALLERY')", name="ck_inspection_source"),
        sa.CheckConstraint("storage_backend IN ('local', 'nextcloud')", name="ck_inspection_storage"),
    )
    op.create_index("ix_inspections_equipment_created", "inspections", ["equipment_id", sa.text("created_at DESC"), sa.text("id DESC")])
    op.create_index("ix_inspections_processing_deadline", "inspections", ["processing_status", "deadline"])


def downgrade():
    raise RuntimeError("Data-destructive downgrade requires an explicit recovery plan")
