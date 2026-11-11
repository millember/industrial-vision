from uuid import uuid4
import os
from dataclasses import dataclass, field
import pytest
from sqlalchemy import select, text
from test_access import client, admin, preview_upload, HEADERS, PASSWORD
from app.infrastructure.database import make_engine, sessions
from app.infrastructure.models import Inspection, Report, Notification, Issue, ReportRequest, Audit, User


@dataclass
class ReportCase:
    saved: dict
    tokens: dict = field(repr=False)
    image: bytes = field(repr=False)


@pytest.fixture
def factory():
    engine = make_engine(os.environ["IV_TEST_DATABASE_URL"])
    yield sessions(engine)
    engine.dispose()


@pytest.fixture
def report_case(client, preview_upload):
    equipment, image = preview_upload
    saved = client.post("/api/v1/inspections", data={"equipment_id":equipment, "source":"CAMERA"},
                        files={"image":("photo.png", image)}, headers={**HEADERS, "Idempotency-Key":str(uuid4())}).json()
    defect = client.post("/api/v1/defect-types", json={"name":"Демо: недокручен", "status":"WARNING",
                         "recommendation":"Проверить демонстрационный макет"}, headers=HEADERS).json()["id"]
    engine = make_engine(os.environ["IV_TEST_DATABASE_URL"])
    with sessions(engine).begin() as db:
        row = db.get(Inspection, saved["inspection_id"])
        row.result = {**row.result, "status":"WARNING", "color":"ORANGE", "defect_id":defect,
                      "defect_code":"DEMO_FASTENER", "defect":"Демо: недокручен", "reason":"Тестовая фикстура MOCK"}
    engine.dispose()
    tokens = {}
    for login, role in (("reporter", "WORKER"), ("master", "MASTER"), ("engineer", "ENGINEER")):
        assert client.post("/api/v1/users", json={"login":login, "password":PASSWORD, "full_name":login,
                           "role":role, "workshop_id":saved["workshop_id"]}, headers=HEADERS).status_code == 201
        tokens[login] = client.post("/api/v1/auth/token", json={"login":login, "password":PASSWORD}).json()["access_token"]
    client.cookies.clear()
    return ReportCase(saved, tokens, image)


def test_report_creates_internal_notifications(client, report_case):
    saved, tokens = report_case.saved, report_case.tokens
    headers = {"Authorization":"Bearer " + tokens["reporter"], "Idempotency-Key":str(uuid4())}
    response = client.post(f"/api/v1/inspections/{saved['inspection_id']}/reports", json={"comment":"Проверьте макет"}, headers=headers)
    assert response.status_code == 201
    result = response.json()
    assert result["analysis_source"] == "MOCK" and result["notification_count"] == 2
    for role in ("master", "engineer"):
        notifications = client.get("/api/v1/notifications", headers={"Authorization":"Bearer " + tokens[role]})
        assert notifications.status_code == 200
        assert notifications.json()["total"] == 1
        assert notifications.json()["items"][0]["report_id"] == result["report_id"]
        assert notifications.json()["items"][0]["message"].startswith("ДЕМО MOCK.")
    assert client.get(f"/api/v1/reports/{result['report_id']}", headers=headers).json()["comment"] == "Проверьте макет"


def test_report_replay_grouping_and_audit(client, report_case, factory):
    saved, tokens = report_case.saved, report_case.tokens
    headers = {"Authorization":"Bearer " + tokens["reporter"], "Idempotency-Key":str(uuid4())}
    url = f"/api/v1/inspections/{saved['inspection_id']}/reports"
    first = client.post(url, json={"comment":"Повтор"}, headers=headers)
    replay = client.post(url, json={"comment":"Повтор"}, headers=headers)
    assert first.status_code == replay.status_code == 201 and first.json() == replay.json()
    conflict = client.post(url, json={"comment":"Другой текст"}, headers=headers)
    assert conflict.status_code == 409 and conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    grouped = client.post(url, json={}, headers={**headers, "Idempotency-Key":str(uuid4())})
    assert grouped.status_code == 201 and grouped.json()["issue_id"] == first.json()["issue_id"]
    assert grouped.json()["notification_status"] == "GROUPED" and grouped.json()["notification_count"] == 0
    with factory() as db:
        assert len(db.scalars(select(Report)).all()) == 2
        assert len(db.scalars(select(Notification)).all()) == 2
        assert len(db.scalars(select(Issue)).all()) == 1
        assert len(db.scalars(select(Audit).where(Audit.action == "report_created")).all()) == 2


@pytest.mark.parametrize("status", ["OK", "UNKNOWN"])
def test_report_rejects_non_problem_and_replays_error(client, report_case, factory, status):
    saved, tokens = report_case.saved, report_case.tokens
    with factory.begin() as db:
        row = db.get(Inspection, saved["inspection_id"])
        row.result = {**row.result, "status":status}
    headers = {"Authorization":"Bearer " + tokens["reporter"], "Idempotency-Key":str(uuid4())}
    url = f"/api/v1/inspections/{saved['inspection_id']}/reports"
    first = client.post(url, json={}, headers=headers)
    assert first.status_code == 409 and first.json()["error"]["code"] == "REPORT_NOT_APPLICABLE"
    with factory.begin() as db:
        row = db.get(Inspection, saved["inspection_id"])
        row.result = {**row.result, "status":"WARNING"}
    replay = client.post(url, json={}, headers=headers)
    assert replay.status_code == 409 and replay.json() == first.json()
    with factory() as db:
        assert not db.scalars(select(Report)).all() and not db.scalars(select(Notification)).all()


def test_report_and_notifications_access_and_read_flags(client, report_case, factory):
    saved, tokens = report_case.saved, report_case.tokens
    headers = {"Authorization":"Bearer " + tokens["reporter"], "Idempotency-Key":str(uuid4())}
    result = client.post(f"/api/v1/inspections/{saved['inspection_id']}/reports", json={}, headers=headers).json()
    master = {"Authorization":"Bearer " + tokens["master"]}
    engineer = {"Authorization":"Bearer " + tokens["engineer"]}
    notification = client.get("/api/v1/notifications", headers=master).json()["items"][0]
    url = f"/api/v1/notifications/{notification['id']}"
    assert client.patch(url, json={"is_read":True}, headers=engineer).status_code == 404
    assert client.patch(url, json={"is_read":"true"}, headers=master).status_code == 422
    assert client.patch(url, json={"is_read":True}, headers=master).json()["is_read"]
    assert client.get("/api/v1/notifications?unread_only=true", headers=master).json()["total"] == 0
    assert not client.patch(url, json={"is_read":False}, headers=master).json()["is_read"]
    assert client.get(f"/api/v1/reports/{result['report_id']}", headers=master).status_code == 200
    with factory.begin() as db:
        # Move the employee out of the workshop; old notifications must no longer be readable.
        db.scalar(select(User).where(User.login == "master")).workshop_id = None
    assert client.get("/api/v1/notifications", headers=master).json()["total"] == 0
    assert client.get(f"/api/v1/reports/{result['report_id']}", headers=master).status_code == 404
    assert client.patch(url, json={"is_read":True}, headers=master).status_code == 404
    assert client.get("/api/v1/notifications").status_code == 401


def test_report_parallel_retries_and_missing_key(client, report_case, factory):
    from concurrent.futures import ThreadPoolExecutor
    saved, tokens = report_case.saved, report_case.tokens
    headers = {"Authorization":"Bearer " + tokens["reporter"], "Idempotency-Key":str(uuid4())}
    url = f"/api/v1/inspections/{saved['inspection_id']}/reports"
    assert client.post(url, json={}, headers={"Authorization":headers["Authorization"]}).status_code == 422
    assert client.post(url, json={"author_id":1}, headers=headers).status_code == 422
    def create(_):
        return client.post(url, json={}, headers=headers)
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(create, range(4)))
    assert all(r.status_code in (201, 409) for r in responses)
    assert any(r.status_code == 201 for r in responses)
    assert all(r.json()["error"]["code"] == "REQUEST_IN_PROGRESS" for r in responses if r.status_code == 409)
    with factory() as db:
        assert len(db.scalars(select(Report)).all()) == 1
        assert len(db.scalars(select(Notification)).all()) == 2


def test_report_rolls_back_all_changes_when_notification_insert_fails(client, report_case, factory):
    saved, tokens = report_case.saved, report_case.tokens
    with factory.begin() as db:
        db.execute(text("ALTER TABLE notifications ADD CONSTRAINT test_report_atomicity CHECK (false) NOT VALID"))
    try:
        response = client.post(f"/api/v1/inspections/{saved['inspection_id']}/reports", json={},
                               headers={"Authorization":"Bearer " + tokens["reporter"], "Idempotency-Key":str(uuid4())})
        assert response.status_code == 409
        with factory() as db:
            for model in (Report, Issue, Notification, ReportRequest):
                assert not db.scalars(select(model)).all()
            assert not db.scalars(select(Audit).where(Audit.action == "report_created")).all()
    finally:
        with factory.begin() as db:
            db.execute(text("ALTER TABLE notifications DROP CONSTRAINT test_report_atomicity"))


def test_report_cross_workshop_and_recipient_selection(client, report_case, factory):
    saved, tokens = report_case.saved, report_case.tokens
    admin(client)
    workshop = client.post("/api/v1/workshops", json={"name":"Чужой цех"}, headers=HEADERS).json()["id"]
    for login, role, workshop_id in (("foreign", "MASTER", workshop), ("head", "HEAD", saved["workshop_id"])):
        assert client.post("/api/v1/users", json={"login":login, "password":PASSWORD, "full_name":login,
                           "role":role, "workshop_id":workshop_id}, headers=HEADERS).status_code == 201
    foreign_token = client.post("/api/v1/auth/token", json={"login":"foreign", "password":PASSWORD}).json()["access_token"]
    with factory.begin() as db:
        db.scalar(select(User).where(User.login == "engineer")).active = False
    client.cookies.clear()
    headers = {"Authorization":"Bearer " + tokens["reporter"], "Idempotency-Key":str(uuid4())}
    result = client.post(f"/api/v1/inspections/{saved['inspection_id']}/reports", json={}, headers=headers).json()
    assert result["notification_count"] == 1
    foreign = {"Authorization":"Bearer " + foreign_token, "Idempotency-Key":str(uuid4())}
    actual = client.get(f"/api/v1/reports/{result['report_id']}", headers=foreign)
    absent = client.get("/api/v1/reports/999999", headers=foreign)
    assert actual.status_code == absent.status_code == 404 and actual.json() == absent.json()
    assert client.post(f"/api/v1/inspections/{saved['inspection_id']}/reports", json={}, headers=foreign).status_code == 404
    assert client.get("/api/v1/notifications", headers=foreign).json()["total"] == 0
    with factory() as db:
        assert len(db.scalars(select(Report)).all()) == 1


def test_mock_and_model_issues_are_grouped_separately(client, report_case, factory):
    saved, tokens = report_case.saved, report_case.tokens
    headers = {"Authorization":"Bearer " + tokens["reporter"], "Idempotency-Key":str(uuid4())}
    url = f"/api/v1/inspections/{saved['inspection_id']}/reports"
    demo = client.post(url, json={}, headers=headers).json()
    with factory.begin() as db:
        row = db.get(Inspection, saved["inspection_id"])
        # Synthetic future MODEL result tests grouping only; no real model is executed.
        row.result = {**row.result, "analysis_source":"MODEL", "model_version":"synthetic-test"}
    real_channel = client.post(url, json={}, headers={**headers, "Idempotency-Key":str(uuid4())})
    assert real_channel.status_code == 201
    assert real_channel.json()["issue_id"] != demo["issue_id"] and real_channel.json()["notification_count"] == 2
    master = {"Authorization":"Bearer " + tokens["master"]}
    items = client.get("/api/v1/notifications", headers=master).json()["items"]
    assert {item["analysis_source"] for item in items} == {"MOCK", "MODEL"}
    assert all(item["created_at"].endswith("Z") for item in items)


def test_reports_from_distinct_inspections_group_atomically(client, report_case, factory):
    from concurrent.futures import ThreadPoolExecutor
    saved, tokens = report_case.saved, report_case.tokens
    headers = {"Authorization":"Bearer " + tokens["reporter"], "Idempotency-Key":str(uuid4())}
    second = client.post("/api/v1/inspections", data={"equipment_id":saved["equipment_id"], "source":"CAMERA"},
                         files={"image":("photo.png", report_case.image)}, headers=headers).json()
    with factory.begin() as db:
        original = db.get(Inspection, saved["inspection_id"]).result
        row = db.get(Inspection, second["inspection_id"])
        row.result = {**row.result, **{key:original[key] for key in ("status", "color", "defect_id", "defect_code", "defect")}}
    def create(inspection_id):
        return client.post(f"/api/v1/inspections/{inspection_id}/reports", json={}, headers=headers)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(create, (saved["inspection_id"], second["inspection_id"])))
    assert all(r.status_code == 201 for r in responses)
    assert responses[0].json()["issue_id"] == responses[1].json()["issue_id"]
    with factory() as db:
        assert len(db.scalars(select(Report)).all()) == 2
        assert len(db.scalars(select(Notification)).all()) == 2
        assert len(db.scalars(select(Issue)).all()) == 1


def test_newly_eligible_recipient_gets_one_notification(client, report_case, factory):
    saved, tokens = report_case.saved, report_case.tokens
    with factory.begin() as db:
        for user in db.scalars(select(User).where(User.role.in_(("MASTER", "ENGINEER")))):
            user.active = False
    headers = {"Authorization":"Bearer " + tokens["reporter"], "Idempotency-Key":str(uuid4())}
    url = f"/api/v1/inspections/{saved['inspection_id']}/reports"
    assert client.post(url, json={}, headers=headers).json()["notification_status"] == "NO_RECIPIENTS"
    with factory.begin() as db:
        db.scalar(select(User).where(User.login == "master")).active = True
    response = client.post(url, json={}, headers={**headers, "Idempotency-Key":str(uuid4())})
    assert response.status_code == 201 and response.json()["notification_count"] == 1
    with factory() as db:
        assert len(db.scalars(select(Notification)).all()) == 1
