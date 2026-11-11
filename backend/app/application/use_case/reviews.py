import hashlib
import json
from app.application.contracts import Account
from app.application.dtos.inspections import InspectionResponse
from app.application.ports.reviews import ReviewRepository, ReviewQueries
from app.domain.errors import AnalysisError
from app.domain.reviews import valid_review


class ReviewUseCase:
    def __init__(self, *, records: ReviewRepository, queries: ReviewQueries):
        self.records, self.queries = records, queries

    def review(self, *, inspection_id: int, actor: Account, key: str, decision: str, status: str,
               comment: str, expected_review_id: int | None) -> InspectionResponse:
        if not valid_review(decision, status, comment):
            raise AnalysisError("VALIDATION_ERROR", "Неверное решение, статус или пустой комментарий")
        request_hash = hashlib.sha256(json.dumps([decision, status, comment, expected_review_id], ensure_ascii=False).encode()).hexdigest()
        return self.records.review(inspection_id=inspection_id, actor=actor, key=key, request_hash=request_hash,
                                   decision=decision, status=status, comment=comment, expected_review_id=expected_review_id)

    def close(self, *, issue_id: int, actor: Account, key: str, reason: str, verification_review_id: int,
              expected_report_id: int, resolution: str) -> InspectionResponse:
        if not reason.strip() or resolution not in ("REPAIRED", "FALSE_ALARM"):
            raise AnalysisError("VALIDATION_ERROR", "Укажите причину закрытия")
        request_hash = hashlib.sha256(json.dumps([reason, verification_review_id, expected_report_id, resolution], ensure_ascii=False).encode()).hexdigest()
        return self.records.close(issue_id=issue_id, actor=actor, key=key, request_hash=request_hash, reason=reason,
                                  verification_review_id=verification_review_id, expected_report_id=expected_report_id, resolution=resolution)

    def history(self, *, inspection_id: int, actor: Account, limit: int, offset: int) -> dict:
        items, total = self.queries.history(inspection_id, actor, limit, offset)
        return {"items":items, "total":total, "limit":limit, "offset":offset}

    def issue(self, *, issue_id: int, actor: Account) -> dict:
        body = self.queries.issue(issue_id, actor)
        if body is None:
            raise AnalysisError("NOT_FOUND", "Проблема не найдена")
        return body
