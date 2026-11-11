import hashlib
from datetime import timezone
from sqlalchemy import select, func
from app.application.contracts import Account
from app.application.dtos.inspections import InspectionResponse
from app.domain.errors import AnalysisError
from .models import Review, WorkflowRequest, Inspection, Issue, Report, Audit
from .queries.reviews import scoped_inspection, scoped_issue
from .issue_lock import lock_issue_group


class PostgresReviewRepository:
    def __init__(self, sessions):
        self.sessions = sessions

    def _cached(self, db, actor: Account, action: str, target_id: int, key: str, request_hash: str) -> InspectionResponse | None:
        lock_key = int.from_bytes(hashlib.sha256(f"workflow:{action}:{actor.id}:{target_id}:{key}".encode()).digest()[:8], "big", signed=True)
        if not db.scalar(select(func.pg_try_advisory_xact_lock(lock_key))):
            raise AnalysisError("REQUEST_IN_PROGRESS", "Операция ещё выполняется")
        old = db.scalar(select(WorkflowRequest).where(WorkflowRequest.author_id == actor.id, WorkflowRequest.action == action,
                        WorkflowRequest.target_id == target_id, WorkflowRequest.key == key))
        if old is None:
            return None
        if old.request_hash != request_hash:
            raise AnalysisError("IDEMPOTENCY_CONFLICT", "Ключ уже использован для другого запроса")
        return InspectionResponse(old.response_status, old.body)

    def _remember(self, db, actor: Account, action: str, target_id: int, key: str, request_hash: str,
                  status: int, body: dict) -> InspectionResponse:
        db.add(WorkflowRequest(author_id=actor.id, action=action, target_id=target_id, key=key,
                               request_hash=request_hash, response_status=status, body=body))
        return InspectionResponse(status, body)

    def review(self, *, inspection_id: int, actor: Account, key: str, request_hash: str, decision: str,
               status: str, comment: str, expected_review_id: int | None) -> InspectionResponse:
        with self.sessions.begin() as db:
            query = scoped_inspection(inspection_id, actor)
            if db.scalar(query) is None:
                raise AnalysisError("NOT_FOUND", "Осмотр не найден")
            if actor.role != "ENGINEER":
                raise AnalysisError("FORBIDDEN", "Проверка доступна только инженеру своего цеха")
            cached = self._cached(db, actor, "review", inspection_id, key, request_hash)
            if cached is not None:
                return cached
            inspection = db.scalar(query.with_for_update(of=Inspection).execution_options(populate_existing=True))
            latest_id = db.scalar(select(Review.id).where(Review.inspection_id == inspection_id).order_by(Review.id.desc()).limit(1))
            if latest_id != expected_review_id:
                body = {"error":{"code":"REVIEW_CONFLICT", "message":"Решение уже изменилось. Обновите осмотр."}}
                return self._remember(db, actor, "review", inspection_id, key, request_hash, 409, body)
            if inspection is None or inspection.processing_status != "COMPLETED" or inspection.result is None:
                body = {"error":{"code":"REVIEW_NOT_APPLICABLE", "message":"Проверять можно только завершённый осмотр"}}
                return self._remember(db, actor, "review", inspection_id, key, request_hash, 409, body)
            row = Review(inspection_id=inspection_id, author_id=actor.id, workshop_id=inspection.workshop_id,
                         decision=decision, status=status, comment=comment, previous_review_id=latest_id, body={})
            db.add(row)
            db.flush()
            body = {"review_id":row.id, "inspection_id":inspection_id, "decision":decision, "status":status,
                    "comment":comment, "author_id":actor.id, "author_name":actor.full_name, "previous_review_id":latest_id,
                    "created_at":row.created_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")}
            row.body = body
            db.add(Audit(user_id=actor.id, action="review_created", entity_id=row.id))
            return self._remember(db, actor, "review", inspection_id, key, request_hash, 201, body)

    def close(self, *, issue_id: int, actor: Account, key: str, request_hash: str, reason: str,
              verification_review_id: int, expected_report_id: int, resolution: str) -> InspectionResponse:
        with self.sessions.begin() as db:
            query = scoped_issue(issue_id, actor)
            initial_issue = db.scalar(query)
            if initial_issue is None:
                raise AnalysisError("NOT_FOUND", "Проблема не найдена")
            if actor.role not in ("MASTER", "ENGINEER"):
                raise AnalysisError("FORBIDDEN", "Закрытие доступно мастеру или инженеру своего цеха")
            cached = self._cached(db, actor, "close", issue_id, key, request_hash)
            if cached is not None:
                return cached
            review = db.get(Review, verification_review_id)
            proof = db.scalar(scoped_inspection(review.inspection_id, actor).with_for_update(of=Inspection)) if review else None
            lock_issue_group(db, initial_issue.equipment_id, initial_issue.workshop_id, initial_issue.defect_type_id, initial_issue.analysis_source)
            issue = db.scalar(query.with_for_update(of=Issue).execution_options(populate_existing=True))
            if issue is None:
                raise AnalysisError("NOT_FOUND", "Проблема не найдена")
            last_report = db.scalar(select(Report).where(Report.issue_id == issue_id).order_by(Report.id.desc()).limit(1))
            error = None
            if issue.closed_at is not None:
                error = ("ISSUE_ALREADY_CLOSED", "Проблема уже закрыта")
            elif last_report is None or last_report.id != expected_report_id:
                error = ("ISSUE_CONFLICT", "Появилось новое сообщение. Обновите проблему.")
            else:
                latest_review = db.scalar(select(Review.id).where(Review.inspection_id == proof.id).order_by(Review.id.desc()).limit(1)) if proof else None
                verified = bool(proof and review and latest_review == review.id and proof.processing_status == "COMPLETED"
                    and proof.equipment_id == issue.equipment_id and proof.workshop_id == issue.workshop_id and proof.result
                    and proof.result.get("analysis_source") == issue.analysis_source)
                if resolution == "REPAIRED":
                    verified = bool(verified and review.decision == "CONFIRMED" and review.status == "OK"
                                    and proof.created_at >= last_report.created_at and review.created_at >= last_report.created_at)
                else:
                    other_inspection = db.scalar(select(Report.id).where(Report.issue_id == issue_id,
                        Report.inspection_id != (proof.id if proof else -1)).limit(1))
                    verified = bool(verified and review.decision == "REJECTED" and review.status == "UNKNOWN"
                                    and review.created_at >= last_report.created_at and other_inspection is None)
                if not verified:
                    error = ("ISSUE_NOT_VERIFIED", "Нужна актуальная проверка того же оборудования и источника анализа")
            if error:
                return self._remember(db, actor, "close", issue_id, key, request_hash, 409, {"error":{"code":error[0], "message":error[1]}})
            issue.closed_at = db.scalar(select(func.clock_timestamp()))
            issue.closed_by, issue.close_review_id, issue.close_reason, issue.resolution = actor.id, review.id, reason, resolution
            body = {"issue_id":issue.id, "equipment_id":issue.equipment_id, "workshop_id":issue.workshop_id,
                    "defect_id":issue.defect_type_id, "analysis_source":issue.analysis_source,
                    "created_at":issue.created_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "latest_report_id":last_report.id, "closed_at":issue.closed_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "closed_by":actor.id, "close_review_id":review.id, "close_reason":reason, "resolution":resolution}
            db.add(Audit(user_id=actor.id, action="issue_closed", entity_id=issue.id))
            return self._remember(db, actor, "close", issue_id, key, request_hash, 200, body)
