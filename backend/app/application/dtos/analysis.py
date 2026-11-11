from dataclasses import dataclass
from datetime import datetime

MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000


@dataclass(frozen=True)
class NormalizedImage:
    content: bytes
    width: int
    height: int
    media_type: str


@dataclass(frozen=True)
class Observation:
    observation: str
    width: int
    height: int
    reason: str
    model_version: str | None = None


@dataclass(frozen=True)
class ImageSize:
    width: int
    height: int


@dataclass(frozen=True)
class PreviewResult:
    equipment_id: int
    object: str
    source: str
    created_at: datetime
    image: ImageSize
    reason: str
    status: str = "UNKNOWN"
    color: str = "GRAY"
    defect: str = "Не удалось определить"
    recommendation: str = "Демонстрационный ответ. Модель не подключена; требуется проверка специалистом."
    analysis_source: str = "MOCK"
    review_status: str = "UNREVIEWED"
    model_version: str | None = None
    defect_id: int | None = None
    defect_code: str | None = None
    box: tuple[int, int, int, int] | None = None
    confidence: float | None = None
