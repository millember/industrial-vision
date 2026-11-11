from uuid import uuid4
import pytest
from sqlalchemy import select, text
from test_access import client, preview_upload
from test_reports import report_case, factory
from app.infrastructure.models import Inspection, Review, Audit, User, WorkflowRequest, Issue


def headers(case, role="engineer", key=None):
    return {"Authorization":"Bearer " + case.tokens[role], "Idempotency-Key":key or str(uuid4())}


def decide(client, case, inspection_id, *, decision="CONFIRMED", status="OK", expected=None, key=None):
    return client.post(f"/api/v1/inspections/{inspection_id}/reviews",
        json={"decision":decision, "status":status, "comment":"Проверено инженером", "expected_review_id":expected},
        headers=headers(case, key=key))


@pytest.fixture
def problem(client, report_case):
    response = client.post(f"/api/v1/inspections/{report_case.saved['inspection_id']}/reports", json={}, headers=headers(report_case, "reporter"))
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def verified_normal(client, report_case, problem):
    response = client.post("/api/v1/inspections", data={"equipment_id":problem["equipment_id"], "source":"CAMERA"},
                           files={"image":("photo.png", report_case.image)}, headers=headers(report_case, "reporter"))
    assert response.status_code == 201
    review = decide(client, report_case, response.json()["inspection_id"])
    assert review.status_code == 201
    return review.json()


def close_body(problem, review, **overrides):
    return {"reason":"Крепление проверено после ремонта", "verification_review_id":review["review_id"],
            "expected_report_id":problem["report_id"], **overrides}


def test_engineer_review_preserves_original(client, report_case):
    saved, tokens = report_case.saved, report_case.tokens
    headers = {"Authorization":"Bearer " + tokens["engineer"], "Idempotency-Key":str(uuid4())}
    before = client.get(f"/api/v1/inspections/{saved['inspection_id']}", headers=headers).json()
    response = client.post(f"/api/v1/inspections/{saved['inspection_id']}/reviews",
        json={"decision":"CONFIRMED", "status":"WARNING", "comment":"Проверено на макете", "expected_review_id":None}, headers=headers)
    assert response.status_code == 201
    current = client.get(f"/api/v1/inspections/{saved['inspection_id']}", headers=headers).json()
    assert current["review_status"] == "CONFIRMED"
    assert current["original_result"] == before
    assert current["latest_review"]["review_id"] == response.json()["review_id"]


def test_review_rejection_history_and_idempotency(client, report_case, factory):
    case = report_case
    inspection_id = case.saved["inspection_id"]
    key = str(uuid4())
    first = decide(client, case, inspection_id, status="WARNING", key=key)
    assert first.status_code == 201
    second = decide(client, case, inspection_id, decision="REJECTED", status="UNKNOWN", expected=first.json()["review_id"])
    assert second.status_code == 201
    assert decide(client, case, inspection_id, status="WARNING", key=key).json() == first.json()
    assert decide(client, case, inspection_id, status="CRITICAL", key=key).status_code == 409
    current = client.get(f"/api/v1/inspections/{inspection_id}", headers=headers(case)).json()
    assert (current["status"], current["color"], current["review_status"], current["defect_id"]) == ("UNKNOWN", "GRAY", "REJECTED", None)
    assert current["original_result"]["status"] == "WARNING"
    history = client.get(f"/api/v1/inspections/{inspection_id}/reviews", headers=headers(case)).json()
    assert history["total"] == 2 and history["items"][0]["previous_review_id"] == first.json()["review_id"]
    equipment_history = client.get(f"/api/v1/equipment/{case.saved['equipment_id']}/inspections", headers=headers(case)).json()
    assert equipment_history["items"][0]["result"]["latest_review"] == second.json()
    assert client.post(f"/api/v1/inspections/{inspection_id}/reports", json={}, headers=headers(case, "reporter")).status_code == 409
    with factory() as db:
        assert db.get(Inspection, inspection_id).result["review_status"] == "UNREVIEWED"


def test_review_optimistic_concurrency(client, report_case, factory):
    from concurrent.futures import ThreadPoolExecutor
    def submit(status):
        return decide(client, report_case, report_case.saved["inspection_id"], status=status)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(submit, ("WARNING", "CRITICAL")))
    assert sorted(r.status_code for r in responses) == [201, 409]
    conflict = next(r for r in responses if r.status_code == 409)
    assert conflict.json()["error"]["code"] == "REVIEW_CONFLICT"
    with factory() as db:
        assert len(db.scalars(select(Review)).all()) == 1


def test_review_permissions_validation_and_scope(client, report_case, factory):
    case = report_case
    url = f"/api/v1/inspections/{case.saved['inspection_id']}/reviews"
    body = {"decision":"CONFIRMED", "status":"WARNING", "comment":"Проверено", "expected_review_id":None}
    assert client.post(url, json=body, headers=headers(case, "reporter")).status_code == 403
    assert client.post(url, json=body, headers=headers(case, "master")).status_code == 403
    assert client.post(url, json={**body, "decision":"REJECTED"}, headers=headers(case)).status_code == 422
    assert client.post(url, json={key:value for key, value in body.items() if key != "expected_review_id"}, headers=headers(case)).status_code == 422
    with factory.begin() as db:
        db.scalar(select(User).where(User.login == "engineer")).workshop_id = None
    foreign = client.post(url, json=body, headers=headers(case))
    absent = client.post("/api/v1/inspections/999999/reviews", json=body, headers=headers(case))
    assert foreign.status_code == absent.status_code == 404 and foreign.json() == absent.json()


def test_close_after_repair_and_replay(client, report_case, problem, verified_normal, factory):
    case = report_case
    url = f"/api/v1/issues/{problem['issue_id']}/close"
    key = str(uuid4())
    body = close_body(problem, verified_normal)
    response = client.post(url, json=body, headers=headers(case, "master", key))
    assert response.status_code == 200
    assert response.json()["resolution"] == "REPAIRED" and response.json()["closed_at"].endswith("Z")
    assert client.post(url, json=body, headers=headers(case, "master", key)).json() == response.json()
    assert client.post(url, json=body, headers=headers(case, "master")).status_code == 409
    visible = client.get(f"/api/v1/issues/{problem['issue_id']}", headers=headers(case, "reporter"))
    assert visible.status_code == 200 and visible.json() == response.json()
    assert client.post(f"/api/v1/inspections/{case.saved['inspection_id']}/reports", json={}, headers=headers(case, "reporter")).status_code == 409
    with factory() as db:
        assert len(db.scalars(select(Audit).where(Audit.action == "issue_closed")).all()) == 1


def test_close_rejects_stale_photo_and_wrong_roles(client, report_case, problem):
    case = report_case
    old_review = decide(client, case, case.saved["inspection_id"]).json()
    body = close_body(problem, old_review)
    url = f"/api/v1/issues/{problem['issue_id']}/close"
    assert client.post(url, json=body, headers=headers(case, "reporter")).status_code == 403
    response = client.post(url, json=body, headers=headers(case, "master"))
    assert response.status_code == 409 and response.json()["error"]["code"] == "ISSUE_NOT_VERIFIED"


def test_close_conflict_on_new_report_and_old_verification(client, report_case, problem, verified_normal):
    case = report_case
    another = client.post(f"/api/v1/inspections/{case.saved['inspection_id']}/reports", json={"comment":"Повторная проблема"},
                           headers=headers(case, "reporter")).json()
    url = f"/api/v1/issues/{problem['issue_id']}/close"
    conflict = client.post(url, json=close_body(problem, verified_normal), headers=headers(case, "master"))
    assert conflict.status_code == 409 and conflict.json()["error"]["code"] == "ISSUE_CONFLICT"
    stale = client.post(url, json=close_body(another, verified_normal), headers=headers(case, "master"))
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "ISSUE_NOT_VERIFIED"


def test_close_false_alarm_is_separate_from_repair(client, report_case, problem):
    review = decide(client, report_case, problem["inspection_id"], decision="REJECTED", status="UNKNOWN").json()
    response = client.post(f"/api/v1/issues/{problem['issue_id']}/close",
        json=close_body(problem, review, resolution="FALSE_ALARM", reason="Первичная оценка ошибочна"), headers=headers(report_case, "engineer"))
    assert response.status_code == 200 and response.json()["resolution"] == "FALSE_ALARM"


def test_review_transaction_rolls_back_if_audit_fails(client, report_case, factory):
    with factory.begin() as db:
        db.execute(text("ALTER TABLE audit_logs ADD CONSTRAINT test_review_atomicity CHECK (action <> 'review_created') NOT VALID"))
    try:
        response = decide(client, report_case, report_case.saved["inspection_id"], status="WARNING")
        assert response.status_code == 409
        with factory() as db:
            assert not db.scalars(select(Review)).all() and not db.scalars(select(WorkflowRequest)).all()
    finally:
        with factory.begin() as db:
            db.execute(text("ALTER TABLE audit_logs DROP CONSTRAINT test_review_atomicity"))


def test_new_defect_after_closure_opens_new_issue(client, report_case, problem, verified_normal, factory):
    case = report_case
    assert client.post(f"/api/v1/issues/{problem['issue_id']}/close", json=close_body(problem, verified_normal), headers=headers(case, "master")).status_code == 200
    new = client.post("/api/v1/inspections", data={"equipment_id":problem["equipment_id"], "source":"CAMERA"},
                      files={"image":("photo.png", case.image)}, headers=headers(case, "reporter")).json()
    with factory.begin() as db:
        original = db.get(Inspection, problem["inspection_id"]).result
        row = db.get(Inspection, new["inspection_id"])
        row.result = {**row.result, **{key:original[key] for key in ("status", "color", "defect_id", "defect_code", "defect")}}
    report = client.post(f"/api/v1/inspections/{new['inspection_id']}/reports", json={}, headers=headers(case, "reporter"))
    assert report.status_code == 201 and report.json()["issue_id"] != problem["issue_id"]
    assert report.json()["notification_count"] == 2


def test_close_and_new_report_cannot_both_commit(client, report_case, problem, verified_normal):
    from concurrent.futures import ThreadPoolExecutor
    case = report_case
    def close():
        return client.post(f"/api/v1/issues/{problem['issue_id']}/close", json=close_body(problem, verified_normal), headers=headers(case, "master"))
    def report():
        return client.post(f"/api/v1/inspections/{problem['inspection_id']}/reports", json={}, headers=headers(case, "reporter"))
    with ThreadPoolExecutor(max_workers=2) as pool:
        close_future, report_future = pool.submit(close), pool.submit(report)
        closed, reported = close_future.result(), report_future.result()
    assert (closed.status_code, reported.status_code) in ((200, 409), (409, 201))


def test_close_rejects_mock_model_mix(client, report_case, problem, verified_normal, factory):
    with factory.begin() as db:
        row = db.get(Inspection, verified_normal["inspection_id"])
        row.result = {**row.result, "analysis_source":"MODEL", "model_version":"synthetic-test"}
    response = client.post(f"/api/v1/issues/{problem['issue_id']}/close", json=close_body(problem, verified_normal), headers=headers(report_case, "master"))
    assert response.status_code == 409 and response.json()["error"]["code"] == "ISSUE_NOT_VERIFIED"


def test_close_rolls_back_if_audit_fails(client, report_case, problem, verified_normal, factory):
    with factory.begin() as db:
        db.execute(text("ALTER TABLE audit_logs ADD CONSTRAINT test_close_atomicity CHECK (action <> 'issue_closed') NOT VALID"))
    try:
        response = client.post(f"/api/v1/issues/{problem['issue_id']}/close", json=close_body(problem, verified_normal), headers=headers(report_case, "master"))
        assert response.status_code == 409
        with factory() as db:
            assert db.get(Issue, problem["issue_id"]).closed_at is None
            assert not db.scalars(select(WorkflowRequest).where(WorkflowRequest.action == "close")).all()
    finally:
        with factory.begin() as db:
            db.execute(text("ALTER TABLE audit_logs DROP CONSTRAINT test_close_atomicity"))
