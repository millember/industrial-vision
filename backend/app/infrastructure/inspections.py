from dataclasses import fields
from datetime import timedelta
from uuid import uuid4
from sqlalchemy import select, update, func
from sqlalchemy.dialects.postgresql import insert
from app.application.dtos.inspections import InspectionRecord
from .models import Inspection, Audit

INSPECTION_COLUMNS = tuple(getattr(Inspection, field.name) for field in fields(InspectionRecord))
INTERRUPTED = {"error":{"code":"ANALYSIS_INTERRUPTED", "message":"Обработка осмотра прервана. Для новой попытки нужен новый ключ."}}


class PostgresInspectionRepository:
    def __init__(self, sessions):
        self.sessions = sessions

    def recover_stale(self) -> None:
        with self.sessions.begin() as db:
            db.execute(update(Inspection).where(Inspection.processing_status == "PROCESSING", Inspection.deadline <= func.now())
                       .values(processing_status="FAILED", error=INTERRUPTED, response_status=503, cleanup_pending=True))

    def reserve(self, *, equipment_id: int, workshop_id: int, author_id: int, source: str,
                key: str, request_hash: str, storage_backend: str) -> tuple[InspectionRecord, bool]:
        self.recover_stale()
        with self.sessions.begin() as db:
            row = db.execute(insert(Inspection).values(
                equipment_id=equipment_id, workshop_id=workshop_id, author_id=author_id, source=source,
                idempotency_key=key, request_hash=request_hash, processing_status="PROCESSING",
                deadline=func.now() + timedelta(minutes=5), photo_key=uuid4().hex, storage_backend=storage_backend,
                cleanup_pending=False,
            ).on_conflict_do_nothing(constraint="uq_inspection_author_key").returning(*INSPECTION_COLUMNS)).mappings().first()
            if row is not None:
                return InspectionRecord(**row), True
            row = db.execute(select(*INSPECTION_COLUMNS).where(Inspection.author_id == author_id, Inspection.idempotency_key == key)).mappings().one()
            return InspectionRecord(**row), False

    def complete(self, inspection_id: int, result: dict, media_type: str, checksum: str) -> bool:
        with self.sessions.begin() as db:
            author_id = db.scalar(update(Inspection).where(Inspection.id == inspection_id, Inspection.processing_status == "PROCESSING",
                                                         Inspection.deadline > func.now())
                                  .values(processing_status="COMPLETED", result=result, response_status=201,
                                          media_type=media_type, checksum=checksum).returning(Inspection.author_id))
            if author_id is None:
                return False
            db.add(Audit(user_id=author_id, action="inspection_completed", entity_id=inspection_id))
            return True

    def fail(self, inspection_id: int, body: dict, status: int, cleanup_pending: bool) -> None:
        with self.sessions.begin() as db:
            db.execute(update(Inspection).where(Inspection.id == inspection_id, Inspection.processing_status == "PROCESSING")
                       .values(processing_status="FAILED", error=body, response_status=status, cleanup_pending=cleanup_pending))
