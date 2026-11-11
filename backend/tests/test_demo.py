from uuid import uuid4
import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from test_access import client, PASSWORD
from test_reports import factory
from app.main import create_app
from app.infrastructure.demo import seed_demo
from app.infrastructure.models import Inspection, User, Workshop


def test_seed_is_explicit_idempotent_and_preserves_existing_accounts(client, factory, monkeypatch):
    monkeypatch.setenv("ANALYSIS_MODE", "disabled")
    with pytest.raises(ValueError, match="ANALYSIS_MODE"):
        seed_demo(factory, PASSWORD)
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Workshop)) == 0
    monkeypatch.setenv("ANALYSIS_MODE", "mock")
    first = seed_demo(factory, PASSWORD)
    assert seed_demo(factory, PASSWORD) == first
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Inspection)) == 4
        previous_hash = db.scalar(select(User.password_hash).where(User.login == "demo_worker"))
    with pytest.raises(ValueError):
        seed_demo(factory, PASSWORD + "different")
    with factory() as db:
        assert db.scalar(select(User.password_hash).where(User.login == "demo_worker")) == previous_hash


def test_demo_workflow_end_to_end_and_restart(client, factory):
    demo = seed_demo(factory, PASSWORD)
    auth = {}
    for role in ("worker", "master", "engineer", "foreign"):
        result = client.post("/api/v1/auth/token", json={"login":"demo_" + role, "password":PASSWORD})
        assert result.status_code == 200
        auth[role] = {"Authorization":"Bearer " + result.json()["access_token"]}
    for scenario, status in (("normal", "OK"), ("warning", "WARNING"), ("critical", "CRITICAL")):
        result = client.get(f"/api/v1/inspections/{demo['inspections'][scenario]}", headers=auth["worker"])
        assert result.status_code == 200
        assert result.json()["status"] == status and result.json()["analysis_source"] == "MOCK"
        assert "Синтетическое" in result.json()["reason"]
    warning = demo["inspections"]["warning"]
    assert client.get(f"/api/v1/inspections/{warning}", headers=auth["foreign"]).status_code == 404
    assert client.get("/docs", headers=auth["worker"]).status_code == 401
    report_headers = {**auth["worker"], "Idempotency-Key":str(uuid4())}
    report = client.post(f"/api/v1/inspections/{warning}/reports", json={"comment":"Проверка демонстрационного макета"}, headers=report_headers)
    assert report.status_code == 201
    assert client.post(f"/api/v1/inspections/{warning}/reports", json={"comment":"Проверка демонстрационного макета"}, headers=report_headers).json() == report.json()
    assert client.get("/api/v1/notifications", headers=auth["master"]).json()["total"] == 1
    decision = client.post(f"/api/v1/inspections/{warning}/reviews", headers={**auth["engineer"],"Idempotency-Key":str(uuid4())},
                           json={"decision":"CONFIRMED","status":"WARNING","comment":"Демо: дефект подтверждён","expected_review_id":None})
    assert decision.status_code == 201
    photo = client.get(f"/api/v1/photos/{warning}", headers=auth["worker"])
    assert photo.status_code == 200
    repair = client.post("/api/v1/inspections", data={"equipment_id":demo["equipment"][1],"source":"CAMERA"},
                         files={"image":("demo.png",photo.content,"image/png")}, headers={**auth["worker"],"Idempotency-Key":str(uuid4())})
    assert repair.status_code == 201 and repair.json()["status"] == "UNKNOWN"
    repair_id = repair.json()["inspection_id"]
    verified = client.post(f"/api/v1/inspections/{repair_id}/reviews", headers={**auth["engineer"],"Idempotency-Key":str(uuid4())},
                           json={"decision":"CONFIRMED","status":"OK","comment":"Демо: после ремонта норма","expected_review_id":None})
    assert verified.status_code == 201
    closed = client.post(f"/api/v1/issues/{report.json()['issue_id']}/close", headers={**auth["master"],"Idempotency-Key":str(uuid4())},
                         json={"reason":"Демо: крепление проверено после ремонта","verification_review_id":verified.json()["review_id"],"expected_report_id":report.json()["report_id"]})
    assert closed.status_code == 200 and closed.json()["resolution"] == "REPAIRED"
    with TestClient(create_app(os.environ["IV_TEST_DATABASE_URL"],secure=False,origin="http://testserver"),base_url="http://testserver") as restarted:
        current = restarted.get(f"/api/v1/inspections/{repair_id}", headers=auth["worker"]).json()
        assert current["status"] == "OK" and current["original_result"]["status"] == "UNKNOWN"
        assert restarted.get(f"/api/v1/issues/{report.json()['issue_id']}", headers=auth["worker"]).json() == closed.json()
        assert restarted.get(f"/api/v1/photos/{warning}", headers=auth["worker"]).content == photo.content
    assert seed_demo(factory, PASSWORD)["inspections"] == demo["inspections"]
