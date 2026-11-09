"""Users, scoped catalogue, browser sessions and API keys."""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None

def upgrade():
    op.create_table("workshops", sa.Column("id", sa.Integer, primary_key=True), sa.Column("name", sa.String(120), unique=True, nullable=False))
    op.create_table("equipment_types", sa.Column("id", sa.Integer, primary_key=True), sa.Column("name", sa.String(120), unique=True, nullable=False))
    op.create_table("users", sa.Column("id", sa.Integer, primary_key=True), sa.Column("login", sa.String(80), unique=True, nullable=False), sa.Column("full_name", sa.String(160), nullable=False), sa.Column("password_hash", sa.Text, nullable=False), sa.Column("role", sa.String(20), nullable=False), sa.Column("workshop_id", sa.Integer, sa.ForeignKey("workshops.id")), sa.Column("active", sa.Boolean, nullable=False))
    op.create_table("equipment", sa.Column("id", sa.Integer, primary_key=True), sa.Column("name", sa.String(160), nullable=False), sa.Column("inventory_number", sa.String(80), unique=True, nullable=False), sa.Column("workshop_id", sa.Integer, sa.ForeignKey("workshops.id"), nullable=False), sa.Column("type_id", sa.Integer, sa.ForeignKey("equipment_types.id"), nullable=False), sa.Column("passport", sa.Text, nullable=False))
    op.create_index("ix_equipment_workshop_id", "equipment", ["workshop_id"])
    op.create_table("defect_types", sa.Column("id", sa.Integer, primary_key=True), sa.Column("name", sa.String(120), unique=True, nullable=False), sa.Column("status", sa.String(16), nullable=False), sa.Column("recommendation", sa.Text, nullable=False))
    op.create_table("browser_sessions", sa.Column("digest", sa.String(64), primary_key=True), sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_browser_sessions_user_id", "browser_sessions", ["user_id"])
    op.create_table("api_keys", sa.Column("id", sa.Integer, primary_key=True), sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False), sa.Column("digest", sa.String(64), unique=True, nullable=False), sa.Column("prefix", sa.String(16), nullable=False), sa.Column("name", sa.String(80), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("revoked", sa.Boolean, nullable=False))
    op.create_index("ix_api_keys_user_id", "api_keys", ["user_id"])
    op.create_table("login_attempts", sa.Column("login", sa.String(80), primary_key=True), sa.Column("failures", sa.Integer, nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("audit_logs", sa.Column("id", sa.Integer, primary_key=True), sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id")), sa.Column("action", sa.String(80), nullable=False), sa.Column("entity_id", sa.Integer), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))

def downgrade():
    raise RuntimeError("Data-destructive downgrade requires an explicit recovery plan")
