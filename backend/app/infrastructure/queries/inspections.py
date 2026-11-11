from sqlalchemy import select, func
from app.application.contracts import Account
from app.application.dtos.inspections import InspectionRecord
from app.infrastructure.models import Inspection, Equipment
from app.infrastructure.inspections import INSPECTION_COLUMNS, PostgresInspectionRepository


class PostgresInspectionQueries:
    def __init__(self, sessions, records: PostgresInspectionRepository):
        self.sessions, self.records = sessions, records

    def get(self, inspection_id: int, actor: Account) -> InspectionRecord | None:
        self.records.recover_stale()
        query = select(*INSPECTION_COLUMNS).join(Equipment, Equipment.id == Inspection.equipment_id).where(Inspection.id == inspection_id)
        if actor.role != "ADMIN":
            query = query.where(Inspection.workshop_id == actor.workshop_id, Equipment.workshop_id == actor.workshop_id)
        with self.sessions() as db:
            row = db.execute(query).mappings().first()
            return InspectionRecord(**row) if row else None

    def history(self, equipment_id: int, actor: Account, limit: int, offset: int) -> tuple[tuple[InspectionRecord, ...], int]:
        self.records.recover_stale()
        conditions = [Inspection.equipment_id == equipment_id]
        if actor.role != "ADMIN":
            conditions.append(Inspection.workshop_id == actor.workshop_id)
        with self.sessions() as db:
            total = db.scalar(select(func.count()).select_from(Inspection).where(*conditions))
            rows = db.execute(select(*INSPECTION_COLUMNS).where(*conditions)
                              .order_by(Inspection.created_at.desc(), Inspection.id.desc()).limit(limit).offset(offset)).mappings()
            return tuple(InspectionRecord(**row) for row in rows), total
