import hashlib
from datetime import timezone
from sqlalchemy import select, func, update
from sqlalchemy.dialects.postgresql import insert
from app.application.contracts import Account
from app.application.dtos.inspections import InspectionResponse
from app.application.dtos.reporting import NotificationRow
from app.domain.errors import AnalysisError
from app.domain.reporting import NOTIFICATION_ROLES, can_report
from app.domain.reviews import reviewed_result
from .models import Inspection, Equipment, DefectType, Issue, Report, ReportRequest, Notification, User, Audit, Review
from .queries.reporting import notification_scope, NOTIFICATION_COLUMNS


class PostgresReportingRepository:
    def __init__(self, sessions):
        self.sessions = sessions

    def create(self, *, inspection_id: int, actor: Account, key: str, request_hash: str, comment: str) -> InspectionResponse:
        lock_key = int.from_bytes(hashlib.sha256(f"report:{actor.id}:{inspection_id}:{key}".encode()).digest()[:8], "big", signed=True)
        with self.sessions.begin() as db:
            query = select(Inspection).join(Equipment, Equipment.id == Inspection.equipment_id).where(Inspection.id == inspection_id)
            if actor.role != "ADMIN":
                query = query.where(Inspection.workshop_id == actor.workshop_id, Equipment.workshop_id == actor.workshop_id)
            inspection = db.scalar(query)
            if inspection is None:
                raise AnalysisError("NOT_FOUND", "Осмотр не найден")
            if not db.scalar(select(func.pg_try_advisory_xact_lock(lock_key))):
                raise AnalysisError("REQUEST_IN_PROGRESS", "Сообщение ещё обрабатывается")
            old = db.scalar(select(ReportRequest).where(ReportRequest.author_id == actor.id,
                            ReportRequest.inspection_id == inspection_id, ReportRequest.key == key))
            if old is not None:
                if old.request_hash != request_hash:
                    raise AnalysisError("IDEMPOTENCY_CONFLICT", "Ключ уже использован для другого запроса")
                return InspectionResponse(old.response_status, old.body)
            inspection = db.scalar(query.with_for_update(of=Inspection).execution_options(populate_existing=True))
            if inspection is None:
                raise AnalysisError("NOT_FOUND", "Осмотр не найден")
            latest_review = db.scalar(select(Review.body).where(Review.inspection_id == inspection_id).order_by(Review.id.desc()).limit(1))
            result = reviewed_result(inspection.result, latest_review) if inspection.result is not None else None
            if not can_report(inspection.processing_status, result) or db.get(DefectType, result["defect_id"]) is None:
                body = {"error":{"code":"REPORT_NOT_APPLICABLE", "message":"Сообщение доступно только для завершённого WARNING/CRITICAL-осмотра с известным дефектом"}}
                db.add(ReportRequest(author_id=actor.id, inspection_id=inspection_id, key=key, request_hash=request_hash, response_status=409, body=body))
                return InspectionResponse(409, body)
            issue_values = {"equipment_id":inspection.equipment_id, "workshop_id":inspection.workshop_id,
                            "defect_type_id":result["defect_id"], "analysis_source":result["analysis_source"]}
            conditions = tuple(getattr(Issue, field) == value for field, value in issue_values.items())
            for _ in range(2):
                closed_at = db.scalar(select(func.max(Issue.closed_at)).where(*conditions))
                if closed_at is not None and inspection.created_at <= closed_at:
                    body = {"error":{"code":"REPORT_NOT_APPLICABLE", "message":"После закрытия проблемы нужен новый осмотр"}}
                    db.add(ReportRequest(author_id=actor.id, inspection_id=inspection_id, key=key, request_hash=request_hash, response_status=409, body=body))
                    return InspectionResponse(409, body)
                issue_id = db.scalar(insert(Issue).values(**issue_values).on_conflict_do_update(
                    index_elements=[Issue.equipment_id, Issue.workshop_id, Issue.defect_type_id, Issue.analysis_source],
                    index_where=Issue.closed_at.is_(None), set_={"equipment_id":inspection.equipment_id},
                    where=Issue.closed_at.is_(None)).returning(Issue.id))
                if issue_id is not None:
                    break
            else:
                raise AnalysisError("REQUEST_IN_PROGRESS", "Проблема изменяется. Повторите запрос.")
            report = Report(inspection_id=inspection_id, issue_id=issue_id, author_id=actor.id,
                            workshop_id=inspection.workshop_id, equipment_id=inspection.equipment_id, comment=comment, body={})
            db.add(report)
            db.flush()
            created_at = report.created_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            prefix = "ДЕМО MOCK. " if result["analysis_source"] == "MOCK" else ""
            message = f"{prefix}{actor.full_name} сообщил о возможной неисправности: {result['object']}. Нужна проверка."
            recipients = tuple(db.scalars(select(User.id).where(User.active.is_(True), User.workshop_id == inspection.workshop_id, User.role.in_(NOTIFICATION_ROLES))))
            count = 0
            if recipients:
                count = len(db.scalars(insert(Notification).values([
                    {"report_id":report.id, "issue_id":issue_id, "recipient_id":recipient_id,
                     "workshop_id":inspection.workshop_id, "message":message, "analysis_source":result["analysis_source"], "is_read":False}
                    for recipient_id in recipients]).on_conflict_do_nothing(constraint="uq_notification_issue_recipient")
                    .returning(Notification.id)).all())
            body = {"report_id":report.id, "inspection_id":inspection_id, "issue_id":issue_id, "author_id":actor.id,
                    "author_name":actor.full_name, "workshop_id":inspection.workshop_id, "equipment_id":inspection.equipment_id,
                    "created_at":created_at, "comment":comment, "status":result["status"], "defect_id":result["defect_id"],
                    "analysis_source":result["analysis_source"], "review_status":result["review_status"],
                    "notification_status":"CREATED" if count else "GROUPED" if recipients else "NO_RECIPIENTS", "notification_count":count}
            report.body = body
            db.add(ReportRequest(author_id=actor.id, inspection_id=inspection_id, key=key, request_hash=request_hash, response_status=201, body=body))
            db.add(Audit(user_id=actor.id, action="report_created", entity_id=report.id))
            return InspectionResponse(201, body)

    def mark_notification(self, *, notification_id: int, actor: Account, is_read: bool) -> NotificationRow | None:
        with self.sessions.begin() as db:
            row = db.execute(update(Notification).where(Notification.id == notification_id, Notification.id.in_(notification_scope(actor)))
                .values(is_read=is_read, read_at=func.coalesce(Notification.read_at, func.now()) if is_read else None)
                .returning(*NOTIFICATION_COLUMNS)).mappings().first()
            return NotificationRow(**row) if row else None
