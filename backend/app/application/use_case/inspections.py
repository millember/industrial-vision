from dataclasses import asdict
from datetime import timezone
import hashlib
import json
from app.application.contracts import Account
from app.application.dtos.inspections import ERROR_STATUS, InspectionRecord, InspectionResponse
from app.application.ports.admin import AdminQueryPort
from app.application.ports.inspections import InspectionRepository, InspectionQueries, PhotoStorage
from app.application.use_case.preview import PreviewInspectionUseCase
from app.domain.errors import AnalysisError
from app.domain.reviews import reviewed_result
from app.application.ports.reviews import ReviewQueries


class InspectionsUseCase:
    def __init__(self, *, catalogue: AdminQueryPort, records: InspectionRepository, queries: InspectionQueries,
                 analyzer: PreviewInspectionUseCase, storage_backend: str, storages: dict[str, PhotoStorage], reviews: ReviewQueries):
        self.catalogue, self.records, self.queries, self.analyzer = catalogue, records, queries, analyzer
        self.storage_backend, self.storages = storage_backend, storages
        self.reviews = reviews

    def create(self, *, equipment_id: int, source: str, content: bytes, key: str, actor: Account) -> InspectionResponse:
        equipment = self.catalogue.equipment(equipment_id, actor)
        if equipment is None:
            raise AnalysisError("NOT_FOUND", "Оборудование не найдено")
        request_hash = hashlib.sha256(json.dumps([equipment_id, source], separators=(",", ":")).encode() + b"\0" + content).hexdigest()
        record, created = self.records.reserve(equipment_id=equipment_id, workshop_id=equipment.workshop_id,
                                               author_id=actor.id, source=source, key=key, request_hash=request_hash,
                                               storage_backend=self.storage_backend)
        if not created:
            if record.request_hash != request_hash:
                raise AnalysisError("IDEMPOTENCY_CONFLICT", "Ключ уже использован для другого запроса")
            return self.response(record)
        storage = self.storages[record.storage_backend]
        write_started = False
        try:
            result, image = self.analyzer.analyze(equipment=equipment, source=source, content=content)
            write_started = True
            storage.put(record.photo_key, image.content, image.media_type)
            body = asdict(result)
            body.update(inspection_id=record.id, photo_id=record.id, author_id=record.author_id,
                        workshop_id=record.workshop_id, created_at=record.created_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"))
            if not self.records.complete(record.id, body, image.media_type, hashlib.sha256(image.content).hexdigest()):
                raise AnalysisError("ANALYSIS_INTERRUPTED", "Обработка осмотра прервана. Для новой попытки нужен новый ключ.")
            return InspectionResponse(201, body)
        except AnalysisError as exc:
            cleanup_pending = write_started
            if write_started:
                try:
                    storage.delete(record.photo_key)
                except AnalysisError:
                    pass  # The failed record keeps its key and cleanup_pending flag.
            body = {"error":{"code":exc.code, "message":str(exc)}}
            self.records.fail(record.id, body, ERROR_STATUS[exc.code], cleanup_pending)
            return InspectionResponse(ERROR_STATUS[exc.code], body)
        except Exception:
            # Preserve programming/database errors, while retaining a recoverable file reference.
            self.records.fail(record.id, {"error":{"code":"ANALYSIS_INTERRUPTED", "message":"Обработка прервана"}}, 503, True)
            raise

    def response(self, record: InspectionRecord) -> InspectionResponse:
        if record.processing_status == "PROCESSING":
            raise AnalysisError("REQUEST_IN_PROGRESS", "Осмотр ещё обрабатывается")
        body = record.result if record.processing_status == "COMPLETED" else record.error
        if record.response_status is None or body is None:
            raise AnalysisError("ANALYSIS_INTERRUPTED", "Результат осмотра недоступен")
        return InspectionResponse(record.response_status, body)

    def get(self, *, inspection_id: int, actor: Account) -> InspectionResponse:
        record = self.queries.get(inspection_id, actor)
        if record is None:
            raise AnalysisError("NOT_FOUND", "Осмотр не найден")
        response = self.response(record)
        body = reviewed_result(response.body, self.reviews.latest((inspection_id,)).get(inspection_id)) if response.status == 201 else response.body
        return InspectionResponse(200 if response.status == 201 else response.status, body)

    def photo(self, *, photo_id: int, actor: Account) -> tuple[bytes, str]:
        record = self.queries.get(photo_id, actor)
        if record is None or record.processing_status != "COMPLETED":
            raise AnalysisError("NOT_FOUND", "Фотография не найдена")
        if record.media_type not in ("image/jpeg", "image/png"):
            raise AnalysisError("STORAGE_UNAVAILABLE", "Метаданные фотографии повреждены")
        storage = self.storages.get(record.storage_backend)
        if storage is None:
            raise AnalysisError("STORAGE_UNAVAILABLE", "Не настроено хранилище сохранённой фотографии")
        content = storage.get(record.photo_key)
        if hashlib.sha256(content).hexdigest() != record.checksum:
            raise AnalysisError("STORAGE_UNAVAILABLE", "Нарушена целостность сохранённой фотографии")
        return content, record.media_type

    def history(self, *, equipment_id: int, actor: Account, limit: int, offset: int) -> dict:
        if self.catalogue.equipment(equipment_id, actor) is None:
            raise AnalysisError("NOT_FOUND", "Оборудование не найдено")
        records, total = self.queries.history(equipment_id, actor, limit, offset)
        reviews = self.reviews.latest(tuple(row.id for row in records))
        items = [{"inspection_id":row.id, "equipment_id":row.equipment_id, "author_id":row.author_id,
                  "workshop_id":row.workshop_id, "source":row.source, "created_at":row.created_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                  "processing_status":row.processing_status,
                  "result":reviewed_result(row.result, reviews.get(row.id)) if row.result is not None else None, "error":row.error} for row in records]
        return {"items":items, "total":total, "limit":limit, "offset":offset}
