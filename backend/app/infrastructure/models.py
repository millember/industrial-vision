from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func, UniqueConstraint, CheckConstraint, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class Workshop(Base):
    __tablename__ = "workshops"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)

class EquipmentType(Base):
    __tablename__ = "equipment_types"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    login: Mapped[str] = mapped_column(String(80), unique=True)
    full_name: Mapped[str] = mapped_column(String(160))
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(20))
    workshop_id: Mapped[int | None] = mapped_column(ForeignKey("workshops.id"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)

class Equipment(Base):
    __tablename__ = "equipment"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    inventory_number: Mapped[str] = mapped_column(String(80), unique=True)
    workshop_id: Mapped[int] = mapped_column(ForeignKey("workshops.id"), index=True)
    type_id: Mapped[int] = mapped_column(ForeignKey("equipment_types.id"))
    passport: Mapped[str] = mapped_column(Text, default="")

class DefectType(Base):
    __tablename__ = "defect_types"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    status: Mapped[str] = mapped_column(String(16))
    recommendation: Mapped[str] = mapped_column(Text)

class BrowserSession(Base):
    __tablename__ = "browser_sessions"
    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class ApiKey(Base):
    __tablename__ = "api_keys"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    digest: Mapped[str] = mapped_column(String(64), unique=True)
    prefix: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)

class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    login: Mapped[str] = mapped_column(String(80), primary_key=True)
    failures: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class Audit(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Inspection(Base):
    __tablename__ = "inspections"
    __table_args__ = (
        UniqueConstraint("author_id", "idempotency_key", name="uq_inspection_author_key"),
        CheckConstraint("processing_status IN ('PROCESSING', 'COMPLETED', 'FAILED')", name="ck_inspection_processing"),
        CheckConstraint("source IN ('CAMERA', 'GALLERY')", name="ck_inspection_source"),
        CheckConstraint("storage_backend IN ('local', 'nextcloud')", name="ck_inspection_storage"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    equipment_id: Mapped[int] = mapped_column(ForeignKey("equipment.id"))
    workshop_id: Mapped[int] = mapped_column(ForeignKey("workshops.id"))
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    source: Mapped[str] = mapped_column(String(16))
    idempotency_key: Mapped[str] = mapped_column(String(36))
    request_hash: Mapped[str] = mapped_column(String(64))
    processing_status: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    photo_key: Mapped[str] = mapped_column(String(32), unique=True)
    storage_backend: Mapped[str] = mapped_column(String(16))
    media_type: Mapped[str | None] = mapped_column(String(32))
    checksum: Mapped[str | None] = mapped_column(String(64))
    result: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    error: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    response_status: Mapped[int | None] = mapped_column(Integer)
    cleanup_pending: Mapped[bool] = mapped_column(Boolean, default=False)


Index("ix_inspections_equipment_created", Inspection.equipment_id, Inspection.created_at.desc(), Inspection.id.desc())
Index("ix_inspections_processing_deadline", Inspection.processing_status, Inspection.deadline)


class Issue(Base):
    __tablename__ = "issues"
    id: Mapped[int] = mapped_column(primary_key=True)
    equipment_id: Mapped[int] = mapped_column(ForeignKey("equipment.id"))
    workshop_id: Mapped[int] = mapped_column(ForeignKey("workshops.id"))
    defect_type_id: Mapped[int] = mapped_column(ForeignKey("defect_types.id"))
    analysis_source: Mapped[str] = mapped_column(String(8))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    close_review_id: Mapped[int | None] = mapped_column(ForeignKey("reviews.id"))
    close_reason: Mapped[str | None] = mapped_column(Text)
    resolution: Mapped[str | None] = mapped_column(String(16))
    __table_args__ = (CheckConstraint("analysis_source IN ('MOCK', 'MODEL')", name="ck_issue_source"),)


Index("uq_open_issue", Issue.equipment_id, Issue.workshop_id, Issue.defect_type_id, Issue.analysis_source,
      unique=True, postgresql_where=Issue.closed_at.is_(None))


class Report(Base):
    __tablename__ = "reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    inspection_id: Mapped[int] = mapped_column(ForeignKey("inspections.id"), index=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id"))
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    workshop_id: Mapped[int] = mapped_column(ForeignKey("workshops.id"))
    equipment_id: Mapped[int] = mapped_column(ForeignKey("equipment.id"))
    comment: Mapped[str] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    body: Mapped[dict] = mapped_column(JSONB)


class ReportRequest(Base):
    __tablename__ = "report_requests"
    __table_args__ = (UniqueConstraint("author_id", "inspection_id", "key", name="uq_report_request"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    inspection_id: Mapped[int] = mapped_column(ForeignKey("inspections.id"))
    key: Mapped[str] = mapped_column(String(36))
    request_hash: Mapped[str] = mapped_column(String(64))
    response_status: Mapped[int] = mapped_column(Integer)
    body: Mapped[dict] = mapped_column(JSONB)


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (UniqueConstraint("issue_id", "recipient_id", name="uq_notification_issue_recipient"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("reports.id"))
    issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id"))
    recipient_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    workshop_id: Mapped[int] = mapped_column(ForeignKey("workshops.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    message: Mapped[str] = mapped_column(Text)
    analysis_source: Mapped[str] = mapped_column(String(8))


Index("ix_notifications_recipient_created", Notification.recipient_id, Notification.created_at.desc(), Notification.id.desc())


class Review(Base):
    __tablename__ = "reviews"
    id: Mapped[int] = mapped_column(primary_key=True)
    inspection_id: Mapped[int] = mapped_column(ForeignKey("inspections.id"))
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    workshop_id: Mapped[int] = mapped_column(ForeignKey("workshops.id"))
    decision: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))
    comment: Mapped[str] = mapped_column(String(2000))
    previous_review_id: Mapped[int | None] = mapped_column(ForeignKey("reviews.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp())
    body: Mapped[dict] = mapped_column(JSONB)
    __table_args__ = (CheckConstraint("(decision = 'CONFIRMED' AND status IN ('OK','WARNING','CRITICAL')) OR (decision = 'REJECTED' AND status = 'UNKNOWN')", name="ck_review_decision"),)


Index("ix_reviews_inspection_id", Review.inspection_id, Review.id.desc())
Index("uq_review_first", Review.inspection_id, unique=True, postgresql_where=Review.previous_review_id.is_(None))
Index("uq_review_successor", Review.previous_review_id, unique=True, postgresql_where=Review.previous_review_id.is_not(None))


class WorkflowRequest(Base):
    __tablename__ = "workflow_requests"
    __table_args__ = (UniqueConstraint("author_id", "action", "target_id", "key", name="uq_workflow_request"),
                      CheckConstraint("action IN ('review', 'close')", name="ck_workflow_action"))
    id: Mapped[int] = mapped_column(primary_key=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(16))
    target_id: Mapped[int] = mapped_column(Integer)
    key: Mapped[str] = mapped_column(String(36))
    request_hash: Mapped[str] = mapped_column(String(64))
    response_status: Mapped[int] = mapped_column(Integer)
    body: Mapped[dict] = mapped_column(JSONB)
