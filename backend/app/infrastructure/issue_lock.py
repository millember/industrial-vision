import hashlib
from sqlalchemy import select, func


def lock_issue_group(db, equipment_id: int, workshop_id: int, defect_id: int, analysis_source: str) -> None:
    """Serialize reporting and closure across old/new issues of the same group."""
    value = f"issue-group:{equipment_id}:{workshop_id}:{defect_id}:{analysis_source}"
    key = int.from_bytes(hashlib.sha256(value.encode()).digest()[:8], "big", signed=True)
    db.execute(select(func.pg_advisory_xact_lock(key)))
