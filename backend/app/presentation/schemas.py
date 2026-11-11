from typing import Literal
from pydantic import BaseModel, Field

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
    inspection_id: int
    photo_id: int
    author_id: int
    workshop_id: int


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
    result: InspectionOut | None
    error: ErrorEnvelope | None


class HistoryOut(BaseModel):
    items: list[HistoryItemOut]
    total: int
    limit: int
    offset: int
