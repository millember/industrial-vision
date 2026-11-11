from datetime import datetime, timezone
from app.application.contracts import Account
from app.application.dtos.analysis import ImageSize, PreviewResult, NormalizedImage
from app.application.dtos.rows import EquipmentRow
from app.application.ports.admin import AdminQueryPort
from app.application.ports.analysis import ImageDecoder, ModelAdapter
from app.domain.errors import AnalysisError


class PreviewInspectionUseCase:
    def __init__(self, *, queries: AdminQueryPort, images: ImageDecoder, model: ModelAdapter | None):
        self.queries, self.images, self.model = queries, images, model

    def execute(self, *, equipment_id: int, source: str, content: bytes, actor: Account) -> PreviewResult:
        equipment = self.queries.equipment(equipment_id, actor)
        if equipment is None:
            raise AnalysisError("NOT_FOUND", "Оборудование не найдено")
        result, _ = self.analyze(equipment=equipment, source=source, content=content)
        return result

    def analyze(self, *, equipment: EquipmentRow, source: str, content: bytes) -> tuple[PreviewResult, NormalizedImage]:
        if self.model is None:
            raise AnalysisError("MODEL_UNAVAILABLE", "Анализ не включён. Модель не подключена.")
        image = self.images.normalize(content)
        observation = self.model.analyze(image)
        if (observation.observation != "UNDETERMINED" or not observation.reason
                or observation.model_version is not None
                or (observation.width, observation.height) != (image.width, image.height)):
            raise AnalysisError("MODEL_INVALID_RESPONSE", "Некорректный ответ адаптера")
        return (PreviewResult(equipment.id, equipment.name, source, datetime.now(timezone.utc),
                              ImageSize(image.width, image.height), observation.reason), image)
