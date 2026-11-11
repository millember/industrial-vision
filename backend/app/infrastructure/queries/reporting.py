from dataclasses import fields
from sqlalchemy import select, func, or_
from app.application.contracts import Account
from app.application.dtos.reporting import NotificationRow, ReportRow
from app.domain.reporting import NOTIFICATION_ROLES, REPORT_READER_ROLES
from app.infrastructure.models import Notification, Report, Equipment

NOTIFICATION_COLUMNS = tuple(getattr(Notification, field.name) for field in fields(NotificationRow))


def notification_scope(actor: Account):
    return select(Notification.id).join(Report, Report.id == Notification.report_id).join(Equipment, Equipment.id == Report.equipment_id).where(
        Notification.recipient_id == actor.id, Notification.workshop_id == actor.workshop_id,
        Equipment.workshop_id == actor.workshop_id, actor.role in NOTIFICATION_ROLES)


class PostgresReportingQueries:
    def __init__(self, sessions):
        self.sessions = sessions

    def report(self, report_id: int, actor: Account) -> ReportRow | None:
        query = select(Report.body).join(Equipment, Equipment.id == Report.equipment_id).where(Report.id == report_id)
        if actor.role != "ADMIN":
            query = query.where(Report.workshop_id == actor.workshop_id, Equipment.workshop_id == actor.workshop_id,
                                or_(Report.author_id == actor.id, actor.role in REPORT_READER_ROLES))
        with self.sessions() as db:
            body = db.scalar(query)
            return ReportRow(body) if body is not None else None

    def notifications(self, actor: Account, limit: int, offset: int, unread_only: bool) -> tuple[tuple[NotificationRow, ...], int]:
        conditions = [Notification.id.in_(notification_scope(actor))]
        if unread_only:
            conditions.append(Notification.is_read.is_(False))
        with self.sessions() as db:
            total = db.scalar(select(func.count()).select_from(Notification).where(*conditions))
            rows = db.execute(select(*NOTIFICATION_COLUMNS).where(*conditions).order_by(Notification.created_at.desc(), Notification.id.desc())
                              .limit(limit).offset(offset)).mappings()
            return tuple(NotificationRow(**row) for row in rows), total
