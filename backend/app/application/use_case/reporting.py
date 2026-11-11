import hashlib
import json
from app.application.contracts import Account
from app.application.dtos.inspections import InspectionResponse
from app.application.dtos.reporting import NotificationRow
from app.application.ports.reporting import ReportingRepository, ReportingQueries
from app.domain.errors import AnalysisError


class ReportingUseCase:
    def __init__(self, *, records: ReportingRepository, queries: ReportingQueries):
        self.records, self.queries = records, queries

    def create(self, *, inspection_id: int, actor: Account, key: str, comment: str) -> InspectionResponse:
        request_hash = hashlib.sha256(json.dumps({"comment":comment}, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
        return self.records.create(inspection_id=inspection_id, actor=actor, key=key, request_hash=request_hash, comment=comment)

    def report(self, *, report_id: int, actor: Account) -> dict:
        row = self.queries.report(report_id, actor)
        if row is None:
            raise AnalysisError("NOT_FOUND", "Сообщение не найдено")
        return row.body

    def notifications(self, *, actor: Account, limit: int, offset: int, unread_only: bool) -> dict:
        rows, total = self.queries.notifications(actor, limit, offset, unread_only)
        return {"items":rows, "total":total, "limit":limit, "offset":offset}

    def mark_notification(self, *, notification_id: int, actor: Account, is_read: bool) -> NotificationRow:
        row = self.records.mark_notification(notification_id=notification_id, actor=actor, is_read=is_read)
        if row is None:
            raise AnalysisError("NOT_FOUND", "Уведомление не найдено")
        return row
