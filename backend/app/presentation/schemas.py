from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, field_serializer

class Login(BaseModel):
    login: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=1, max_length=256)


class NewUser(Login):
    password: str = Field(min_length=12, max_length=256)
    full_name: str = Field(min_length=1, max_length=160)
    role: Literal["ADMIN", "WORKER", "MASTER", "ENGINEER", "HEAD"] = "WORKER"
    workshop_id: int | None = Field(default=None, gt=0)


class Named(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class NewKey(Named):
    name: str = Field(min_length=1, max_length=80)
    days: int = Field(default=30, ge=1, le=365)


class NewEquipment(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    inventory_number: str = Field(min_length=1, max_length=80)
    workshop_id: int = Field(gt=0)
    type_id: int = Field(gt=0)
    passport: str = Field(default="", max_length=10000)


class NewDefect(Named):
    status: Literal["WARNING", "CRITICAL"]
    recommendation: str = Field(min_length=1, max_length=4000)


from datetime import datetime
class AccountOut(BaseModel):
    id:int
    login:str
    full_name:str
    role:str
    workshop_id:int|None


class MobileTokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"]
    expires_in: int
    user: AccountOut


class IdOut(BaseModel):
    id: int


class HealthOut(BaseModel):
    status: Literal["ok"]


class UserOut(AccountOut):
    active:bool
class KeyOut(BaseModel):
    id:int
    name:str
    prefix:str
    created_at:datetime
    expires_at:datetime
    revoked:bool
class IssuedKeyOut(BaseModel):
    id:int
    key:str
    expires_at:datetime
class NamedOut(Named):
    id:int
class EquipmentOut(NewEquipment):
    id:int
class DefectOut(NewDefect):
    id:int


class ImageSizeOut(BaseModel):
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class PreviewOut(BaseModel):
    equipment_id: int
    object: str
    source: Literal["CAMERA", "GALLERY"]
    created_at: datetime
    image: ImageSizeOut
    reason: str
    status: Literal["UNKNOWN"]
    color: Literal["GRAY"]
    defect: str
    recommendation: str
    analysis_source: Literal["MOCK"]
    review_status: Literal["UNREVIEWED"]
    model_version: None
    defect_id: None
    defect_code: None
    box: None
    confidence: None


class InspectionOut(PreviewOut):
    status: Literal["OK", "WARNING", "CRITICAL", "UNKNOWN"]
    color: Literal["GREEN", "ORANGE", "RED", "GRAY"]
    analysis_source: Literal["MOCK", "MODEL"]
    model_version: str | None
    review_status: Literal["UNREVIEWED", "CONFIRMED", "REJECTED"]
    defect_id: int | None
    defect_code: str | None
    box: tuple[int, int, int, int] | None
    confidence: float | None = Field(ge=0, le=1)
    inspection_id: int
    photo_id: int
    author_id: int
    workshop_id: int


class ReviewOut(BaseModel):
    review_id: int
    inspection_id: int
    decision: Literal["CONFIRMED", "REJECTED"]
    status: Literal["OK", "WARNING", "CRITICAL", "UNKNOWN"]
    comment: str
    author_id: int
    author_name: str
    previous_review_id: int | None
    created_at: datetime


class InspectionDetailOut(InspectionOut):
    original_result: InspectionOut | None = None
    latest_review: ReviewOut | None = None


class NewReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["CONFIRMED", "REJECTED"]
    status: Literal["OK", "WARNING", "CRITICAL", "UNKNOWN"]
    comment: str = Field(min_length=1, max_length=2000, pattern=r"\S")
    expected_review_id: int | None = Field(..., gt=0, strict=True)


class ReviewsOut(BaseModel):
    items: list[ReviewOut]
    total: int
    limit: int
    offset: int


class CloseIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1, max_length=2000, pattern=r"\S")
    verification_review_id: int = Field(gt=0, strict=True)
    expected_report_id: int = Field(gt=0, strict=True)
    resolution: Literal["REPAIRED", "FALSE_ALARM"] = "REPAIRED"


class IssueOut(BaseModel):
    issue_id: int
    equipment_id: int
    workshop_id: int
    defect_id: int
    analysis_source: Literal["MOCK", "MODEL"]
    created_at: datetime
    latest_report_id: int | None
    closed_at: datetime | None
    closed_by: int | None
    close_review_id: int | None
    close_reason: str | None
    resolution: Literal["REPAIRED", "FALSE_ALARM"] | None

    @field_serializer("created_at", "closed_at")
    def utc_time(self, value: datetime | None) -> str | None:
        from datetime import timezone
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if value is not None else None


class AnalysisErrorOut(BaseModel):
    code: str
    message: str


class ErrorEnvelope(BaseModel):
    error: AnalysisErrorOut


class HistoryItemOut(BaseModel):
    inspection_id: int
    equipment_id: int
    author_id: int
    workshop_id: int
    source: Literal["CAMERA", "GALLERY"]
    created_at: datetime
    processing_status: Literal["PROCESSING", "COMPLETED", "FAILED"]
    result: InspectionDetailOut | None
    error: ErrorEnvelope | None


class HistoryOut(BaseModel):
    items: list[HistoryItemOut]
    total: int
    limit: int
    offset: int


class NewReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    comment: str = Field(default="", max_length=2000)


class ReportOut(BaseModel):
    report_id: int
    inspection_id: int
    issue_id: int
    author_id: int
    author_name: str
    workshop_id: int
    equipment_id: int
    created_at: datetime
    comment: str
    status: Literal["WARNING", "CRITICAL"]
    defect_id: int
    analysis_source: Literal["MOCK", "MODEL"]
    review_status: Literal["UNREVIEWED", "CONFIRMED"]
    notification_status: Literal["CREATED", "GROUPED", "NO_RECIPIENTS"]
    notification_count: int


class NotificationOut(BaseModel):
    id: int
    report_id: int
    issue_id: int
    created_at: datetime
    is_read: bool
    read_at: datetime | None
    message: str
    analysis_source: Literal["MOCK", "MODEL"]

    @field_serializer("created_at", "read_at")
    def utc_time(self, value: datetime | None) -> str | None:
        from datetime import timezone
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if value is not None else None


class NotificationsOut(BaseModel):
    items: list[NotificationOut]
    total: int
    limit: int
    offset: int


class NotificationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_read: bool = Field(strict=True)
