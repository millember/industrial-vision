from typing import Protocol
from app.application.contracts import Account
from app.application.dtos.inspections import InspectionResponse
from app.application.dtos.reporting import NotificationRow, ReportRow


class ReportingRepository(Protocol):
    def create(self, *, inspection_id: int, actor: Account, key: str, request_hash: str, comment: str) -> InspectionResponse: ...
    def mark_notification(self, *, notification_id: int, actor: Account, is_read: bool) -> NotificationRow | None: ...


class ReportingQueries(Protocol):
    def report(self, report_id: int, actor: Account) -> ReportRow | None: ...
    def notifications(self, actor: Account, limit: int, offset: int, unread_only: bool) -> tuple[tuple[NotificationRow, ...], int]: ...
