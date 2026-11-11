from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ReportRow:
    body: dict


@dataclass(frozen=True)
class NotificationRow:
    id: int
    report_id: int
    issue_id: int
    created_at: datetime
    is_read: bool
    read_at: datetime | None
    message: str
    analysis_source: str
