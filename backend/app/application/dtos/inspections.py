from dataclasses import dataclass
from datetime import datetime
from typing import Any

ERROR_STATUS = {
    "VALIDATION_ERROR":422, "INVALID_IMAGE":422, "UNSUPPORTED_IMAGE_TYPE":415,
    "IMAGE_TOO_LARGE":413, "NOT_FOUND":404, "MODEL_UNAVAILABLE":503,
    "MODEL_INVALID_RESPONSE":502, "STORAGE_UNAVAILABLE":503,
    "IDEMPOTENCY_CONFLICT":409, "REQUEST_IN_PROGRESS":409, "ANALYSIS_INTERRUPTED":503,
    "REPORT_NOT_APPLICABLE":409,
}


@dataclass(frozen=True)
class InspectionRecord:
    id: int
    equipment_id: int
    workshop_id: int
    author_id: int
    source: str
    request_hash: str
    processing_status: str
    created_at: datetime
    photo_key: str
    storage_backend: str
    media_type: str | None
    checksum: str | None
    result: dict[str, Any] | None
    error: dict[str, Any] | None
    response_status: int | None


@dataclass(frozen=True)
class InspectionResponse:
    status: int
    body: dict[str, Any]
