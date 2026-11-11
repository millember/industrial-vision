from sqlalchemy import select, func, exists, or_
from app.application.contracts import Account
from app.domain.errors import AnalysisError
from app.domain.reporting import REPORT_READER_ROLES
from app.infrastructure.models import Review, Inspection, Equipment, Issue, Report


def scoped_inspection(inspection_id: int, actor: Account):
    query = select(Inspection).join(Equipment, Equipment.id == Inspection.equipment_id).where(Inspection.id == inspection_id)
    if actor.role != "ADMIN":
        query = query.where(Inspection.workshop_id == actor.workshop_id, Equipment.workshop_id == actor.workshop_id)
    return query


def scoped_issue(issue_id: int, actor: Account):
    query = select(Issue).join(Equipment, Equipment.id == Issue.equipment_id).where(Issue.id == issue_id)
    if actor.role != "ADMIN":
        query = query.where(Issue.workshop_id == actor.workshop_id, Equipment.workshop_id == actor.workshop_id,
                            or_(actor.role in REPORT_READER_ROLES, exists(select(Report.id).where(Report.issue_id == Issue.id, Report.author_id == actor.id))))
    return query


class PostgresReviewQueries:
    def __init__(self, sessions):
        self.sessions = sessions

    def latest(self, inspection_ids: tuple[int, ...]) -> dict[int, dict]:
        if not inspection_ids:
            return {}
        with self.sessions() as db:
            latest_ids = select(func.max(Review.id)).where(Review.inspection_id.in_(inspection_ids)).group_by(Review.inspection_id)
            rows = db.execute(select(Review.inspection_id, Review.body).where(Review.id.in_(latest_ids)))
            return {inspection_id:body for inspection_id, body in rows}

    def history(self, inspection_id: int, actor: Account, limit: int, offset: int) -> tuple[tuple[dict, ...], int]:
        with self.sessions() as db:
            if db.scalar(scoped_inspection(inspection_id, actor)) is None:
                raise AnalysisError("NOT_FOUND", "Осмотр не найден")
            total = db.scalar(select(func.count()).select_from(Review).where(Review.inspection_id == inspection_id))
            items = tuple(db.scalars(select(Review.body).where(Review.inspection_id == inspection_id).order_by(Review.id.desc()).limit(limit).offset(offset)))
            return items, total

    def issue(self, issue_id: int, actor: Account) -> dict | None:
        with self.sessions() as db:
            row = db.scalar(scoped_issue(issue_id, actor))
            if row is None:
                return None
            latest_report = db.scalar(select(func.max(Report.id)).where(Report.issue_id == issue_id))
            return {"issue_id":row.id, "equipment_id":row.equipment_id, "workshop_id":row.workshop_id,
                    "defect_id":row.defect_type_id, "analysis_source":row.analysis_source, "created_at":row.created_at,
                    "latest_report_id":latest_report, "closed_at":row.closed_at, "closed_by":row.closed_by,
                    "close_review_id":row.close_review_id, "close_reason":row.close_reason, "resolution":row.resolution}
