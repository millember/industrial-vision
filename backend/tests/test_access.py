
import os
from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text, select
from app.main import create_app
from app.infrastructure.database import make_engine, sessions
from app.infrastructure.repository import Repository
from app.infrastructure.models import ApiKey, BrowserSession, User
from app.application.auth import digest
from app.infrastructure.passwords import Passwords

PASSWORD = "Example-Test-Password-2026!"
HEADERS = {"Origin":"http://testserver","X-IV-Client":"browser"}

@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("ANALYSIS_MODE", "mock")
    monkeypatch.setenv("PHOTO_STORAGE", "local")
    monkeypatch.setenv("PHOTO_ROOT", str(tmp_path / "photos"))
    url=os.environ["IV_TEST_DATABASE_URL"]
    assert url.split("/")[-1] == "iv_step2_test", "Only the isolated test database may be reset"
    with TestClient(create_app(url,secure=False,origin="http://testserver"),base_url="http://testserver") as client:
        engine=make_engine(url)
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE audit_logs, api_keys, browser_sessions, login_attempts, equipment, users, defect_types, equipment_types, workshops RESTART IDENTITY CASCADE"))
        repo=Repository(sessions(engine))
        repo.create_user({"login":"admin","full_name":"Test admin","role":"ADMIN","password_hash":Passwords().hash(PASSWORD),"workshop_id":None,"active":True})
        yield client
        engine.dispose()

def admin(client):
    result=client.post("/api/v1/auth/login",json={"login":"admin","password":PASSWORD},headers=HEADERS)
    assert result.status_code==200
    return result

def test_anonymous_is_denied(client):
    for path in ("/docs","/openapi.json","/redoc","/api/v1/users","/api/v1/keys","/api/v1/auth/me","/api/v1/equipment","/api/v1/health"):
        assert client.get(path).status_code==401, path
    assert client.get("/healthz").json()=={"status":"ok"}

def test_admin_cookie_docs_and_logout(client):
    result=admin(client)
    cookie=result.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert "password_hash" not in result.json()
    assert client.get("/docs").status_code==200
    assert "/api/v1/users" in client.get("/openapi.json").json()["paths"]
    assert client.post("/api/v1/auth/logout",headers=HEADERS).status_code==204
    assert client.get("/docs").status_code==401

def test_csrf_and_bad_login(client):
    assert client.post("/api/v1/auth/login",json={"login":"admin","password":PASSWORD}).status_code==403
    for _ in range(5):
        assert client.post("/api/v1/auth/login",json={"login":"admin","password":"wrong"},headers=HEADERS).status_code==401
    assert client.post("/api/v1/auth/login",json={"login":"admin","password":PASSWORD},headers=HEADERS).status_code==429

def test_issue_and_revoke_key(client):
    admin(client)
    result=client.post("/api/v1/keys",json={"name":"Android integration","days":30},headers=HEADERS)
    assert result.status_code==201
    key=result.json()
    assert key["key"].startswith("iv_k_")
    listed=client.get("/api/v1/keys").json()
    assert listed[0]["prefix"]==key["key"][:12] and "key" not in listed[0] and "digest" not in listed[0]
    with sessions(make_engine(os.environ["IV_TEST_DATABASE_URL"]))() as db:
        assert db.scalar(select(ApiKey)).digest != key["key"]
        expires_at = db.scalar(select(ApiKey.expires_at))
    client.cookies.clear()
    headers={"Authorization":"Bearer "+key["key"]}
    assert client.get("/api/v1/health",headers=headers).status_code==200
    with sessions(make_engine(os.environ["IV_TEST_DATABASE_URL"]))() as db:
        assert db.scalar(select(ApiKey.expires_at)) == expires_at
    assert client.get("/docs",headers=headers).status_code==401
    assert client.post("/api/v1/keys",headers={**headers,**HEADERS},json={"name":"forbidden"}).status_code==401
    admin(client)
    assert client.delete("/api/v1/keys/"+str(key["id"]),headers=HEADERS).status_code==204
    client.cookies.clear()
    assert client.get("/api/v1/health",headers=headers).status_code==401

def test_employee_mobile_only_and_scoping(client):
    admin(client)
    w1=client.post("/api/v1/workshops",json={"name":"Workshop 1"},headers=HEADERS).json()["id"]
    w2=client.post("/api/v1/workshops",json={"name":"Workshop 2"},headers=HEADERS).json()["id"]
    typ=client.post("/api/v1/equipment-types",json={"name":"Fastener"},headers=HEADERS).json()["id"]
    for number,workshop in enumerate((w1,w2),1):
        assert client.post("/api/v1/equipment",json={"name":"Unit","inventory_number":str(number),"workshop_id":workshop,"type_id":typ},headers=HEADERS).status_code==201
    user={"login":"worker","password":PASSWORD,"full_name":"Test employee","role":"WORKER","workshop_id":w1}
    assert client.post("/api/v1/users",json=user,headers=HEADERS).status_code==201
    assert client.post("/api/v1/users",json=user,headers=HEADERS).status_code==409
    client.cookies.clear()
    assert client.post("/api/v1/auth/login",json={"login":"worker","password":PASSWORD},headers=HEADERS).status_code==403
    token=client.post("/api/v1/auth/token",json={"login":"worker","password":PASSWORD})
    assert token.status_code==200
    headers={"Authorization":"Bearer "+token.json()["access_token"]}
    assert client.get("/api/v1/me",headers=headers).json()["login"]=="worker"
    assert [x["workshop_id"] for x in client.get("/api/v1/equipment",headers=headers).json()]==[w1]
    for path in ("/docs","/openapi.json","/api/v1/users","/api/v1/keys","/api/v1/auth/me"):
        assert client.get(path,headers=headers).status_code==401
    assert client.post("/api/v1/workshops",json={"name":"Denied"},headers={**headers,**HEADERS}).status_code==401

def test_token_expiry_and_inactive_user(client):
    from datetime import datetime, timedelta, timezone
    admin(client)
    with sessions(make_engine(os.environ["IV_TEST_DATABASE_URL"])).begin() as db:
        for row in db.scalars(select(BrowserSession)):row.expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)
    assert client.get("/docs").status_code==401

def test_secure_cookie(client):
    url=os.environ["IV_TEST_DATABASE_URL"]
    with TestClient(create_app(url,secure=True,origin="https://testserver"),base_url="https://testserver") as secure_client:
        r=secure_client.post("/api/v1/auth/login",json={"login":"admin","password":PASSWORD},headers={"Origin":"https://testserver","X-IV-Client":"browser"})
        assert r.status_code==200 and "secure" in r.headers["set-cookie"].lower()

@pytest.mark.parametrize("mobile", [True, False], ids=["bearer", "cookie"])
def test_session_lifetime_and_sliding_expiry(client, mobile):
    before = datetime.now(timezone.utc)
    if mobile:
        response = client.post("/api/v1/auth/token", json={"login":"admin", "password":PASSWORD})
        assert response.json()["expires_in"] == 86400
        token = response.json()["access_token"]
        headers = {"Authorization": "Bearer " + token}
        path = "/api/v1/me"
    else:
        response = admin(client)
        assert "Max-Age=86400" in response.headers["set-cookie"]
        token = client.cookies.get("iv_admin_session")
        headers = {}
        path = "/docs"
    engine = make_engine(os.environ["IV_TEST_DATABASE_URL"])
    factory = sessions(engine)
    with factory.begin() as db:
        row = db.scalar(select(BrowserSession).where(BrowserSession.digest == digest(token)))
        assert before + timedelta(hours=24) <= row.expires_at <= datetime.now(timezone.utc) + timedelta(hours=24)
        row.expires_at = datetime.now(timezone.utc) + timedelta(minutes=1)
    before = datetime.now(timezone.utc)
    renewed = client.get(path, headers=headers)
    assert renewed.status_code == 200
    if not mobile:
        assert "Max-Age=86400" in renewed.headers["set-cookie"]
        assert client.cookies.get("iv_admin_session") == token
    with factory.begin() as db:
        row = db.scalar(select(BrowserSession).where(BrowserSession.digest == digest(token)))
        assert before + timedelta(hours=24) <= row.expires_at <= datetime.now(timezone.utc) + timedelta(hours=24)
        expired_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        row.expires_at = expired_at
    assert client.get(path, headers=headers).status_code == 401
    with factory() as db:
        assert db.scalar(select(BrowserSession.expires_at).where(BrowserSession.digest == digest(token))) == expired_at
    engine.dispose()

def test_inactive_user_cannot_renew_session(client):
    response = client.post("/api/v1/auth/token", json={"login":"admin", "password":PASSWORD})
    token = response.json()["access_token"]
    engine = make_engine(os.environ["IV_TEST_DATABASE_URL"])
    factory = sessions(engine)
    with factory.begin() as db:
        db.scalar(select(User).where(User.login == "admin")).active = False
        original = db.scalar(select(BrowserSession.expires_at))
    assert client.get("/api/v1/me", headers={"Authorization":"Bearer " + token}).status_code == 401
    with factory() as db:
        assert db.scalar(select(BrowserSession.expires_at)) == original
    engine.dispose()

@pytest.mark.parametrize("role", ["WORKER", "MASTER", "ENGINEER", "HEAD", "ADMIN"])
def test_equipment_card_and_knowledge_access(client, role):
    admin(client)
    workshop_ids = [
        client.post("/api/v1/workshops", json={"name": name}, headers=HEADERS).json()["id"]
        for name in ("Цех 1", "Цех 2")
    ]
    type_id = client.post("/api/v1/equipment-types", json={"name":"Макет"}, headers=HEADERS).json()["id"]
    cards = []
    for i, workshop_id in enumerate(workshop_ids):
        values = {"name":"Макет узла", "inventory_number":f"DEMO-{i}",
                  "workshop_id":workshop_id, "type_id":type_id, "passport":"Демонстрационный макет, крепление М6."}
        response = client.post("/api/v1/equipment", json=values, headers=HEADERS)
        assert response.status_code == 201
        cards.append({"id":response.json()["id"], **values})
    defects = []
    for status, name, recommendation in (
        ("WARNING", "Недокручен", "На демонстрационном макете докрутить крепёж."),
        ("CRITICAL", "Отсутствует", "Проверить крепление демонстрационного макета."),
    ):
        values = {"name":name, "status":status, "recommendation":recommendation}
        response = client.post("/api/v1/defect-types", json=values, headers=HEADERS)
        assert response.status_code == 201
        defects.append({"id":response.json()["id"], **values})
    # The browser administrator can read equipment from either workshop.
    for card in cards:
        response = client.get(f"/api/v1/equipment/{card['id']}")
        assert response.status_code == 200
        assert response.json() == card
    user = {"login":"reader", "password":PASSWORD, "full_name":"Читатель", "role":role,
            "workshop_id":None if role == "ADMIN" else workshop_ids[0]}
    assert client.post("/api/v1/users", json=user, headers=HEADERS).status_code == 201
    client.cookies.clear()
    assert client.get(f"/api/v1/equipment/{cards[0]['id']}").status_code == 401
    assert client.get("/api/v1/defect-types").status_code == 401
    token = client.post("/api/v1/auth/token", json={"login":"reader", "password":PASSWORD}).json()["access_token"]
    headers = {"Authorization":"Bearer " + token}
    assert client.get(f"/api/v1/equipment/{cards[0]['id']}", headers=headers).json() == cards[0]
    missing = client.get("/api/v1/equipment/999999", headers=headers)
    assert missing.status_code == 404
    other = client.get(f"/api/v1/equipment/{cards[1]['id']}", headers=headers)
    if role == "ADMIN":
        assert other.status_code == 200 and other.json() == cards[1]
    else:
        assert other.status_code == 404 and other.json() == missing.json()
    assert client.get("/api/v1/defect-types", headers=headers).json() == defects

@pytest.fixture
def preview_upload(client):
    from io import BytesIO
    from PIL import Image
    admin(client)
    workshop = client.post("/api/v1/workshops", json={"name":"Цех"}, headers=HEADERS).json()["id"]
    typ = client.post("/api/v1/equipment-types", json={"name":"Макет"}, headers=HEADERS).json()["id"]
    equipment = client.post("/api/v1/equipment", json={"name":"Макет", "inventory_number":"PREVIEW",
                            "workshop_id":workshop, "type_id":typ}, headers=HEADERS).json()["id"]
    image = BytesIO()
    Image.new("RGB", (32, 24)).save(image, format="PNG")
    return equipment, image.getvalue()


@pytest.mark.parametrize("source", ["CAMERA", "GALLERY"])
def test_photo_preview(client, preview_upload, source):
    equipment, image = preview_upload
    # The decoded bytes determine the image type, not filename or MIME.
    response = client.post("/api/v1/inspections/preview", data={"equipment_id":equipment, "source":source},
                           files={"image":("photo.txt", image, "application/octet-stream")}, headers=HEADERS)
    assert response.status_code == 200
    result = response.json()
    assert result["equipment_id"] == equipment
    assert result["analysis_source"] == "MOCK" and result["model_version"] is None
    assert result["status"] == "UNKNOWN" and result["color"] == "GRAY"
    assert result["image"] == {"width":32, "height":24}
    assert "inspection_id" not in result and "photo_id" not in result


@pytest.mark.parametrize("data,content,expected,code", [
    ({"source":"FILE"}, None, 422, "VALIDATION_ERROR"),
    ({"equipment_id":"0"}, None, 422, "VALIDATION_ERROR"),
    ({"extra":"ignored?"}, None, 422, "VALIDATION_ERROR"),
    ({}, b"", 422, "INVALID_IMAGE"),
    ({}, b"\xff\xd8broken", 422, "INVALID_IMAGE"),
    ({}, b"not an image", 415, "UNSUPPORTED_IMAGE_TYPE"),
])
def test_photo_preview_rejects_bad_input(client, preview_upload, data, content, expected, code):
    equipment, image = preview_upload
    response = client.post("/api/v1/inspections/preview",
                           data={"equipment_id":equipment, "source":"CAMERA", **data},
                           files={"image":("photo.png", image if content is None else content, "image/png")}, headers=HEADERS)
    assert response.status_code == expected
    assert response.json()["error"]["code"] == code


def test_photo_preview_authentication_and_csrf(client, preview_upload):
    equipment, image = preview_upload
    data = {"equipment_id":equipment, "source":"CAMERA"}
    files = {"image":("photo.png", image, "image/png")}
    response = client.post("/api/v1/inspections/preview", data=data, files=files)
    assert response.status_code == 403 and response.json()["error"]["code"] == "FORBIDDEN"
    response = client.post("/api/v1/inspections/preview", data=data, files=files,
                           headers={"Authorization":"Basic invalid"})
    assert response.status_code == 403
    client.cookies.clear()
    response = client.post("/api/v1/inspections/preview", data=data, files=files)
    assert response.status_code == 401 and response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_photo_preview_cross_workshop_is_hidden(client, preview_upload):
    equipment, image = preview_upload
    workshop = client.post("/api/v1/workshops", json={"name":"Другой цех"}, headers=HEADERS).json()["id"]
    user = {"login":"worker", "password":PASSWORD, "full_name":"Рабочий", "role":"WORKER", "workshop_id":workshop}
    assert client.post("/api/v1/users", json=user, headers=HEADERS).status_code == 201
    token = client.post("/api/v1/auth/token", json={"login":"worker", "password":PASSWORD}).json()["access_token"]
    client.cookies.clear()
    headers = {"Authorization":"Bearer " + token}
    responses = [client.post("/api/v1/inspections/preview", data={"equipment_id":i, "source":"GALLERY"},
                             files={"image":("photo.png", b"invalid image", "image/png")}, headers=headers)
                 for i in (equipment, 999999)]
    assert all(r.status_code == 404 for r in responses)
    assert responses[0].json() == responses[1].json()
    # Giving the employee equipment in their own workshop permits preview.
    admin(client)
    own = client.post("/api/v1/equipment", json={"name":"Свой макет", "inventory_number":"OWN",
                      "workshop_id":workshop, "type_id":1}, headers=HEADERS).json()["id"]
    client.cookies.clear()
    assert client.post("/api/v1/inspections/preview", data={"equipment_id":own, "source":"GALLERY"},
                       files={"image":("photo.png", image, "image/png")}, headers=headers).status_code == 200


def test_photo_preview_requires_explicit_mock_mode(client, preview_upload, monkeypatch):
    equipment, image = preview_upload
    token = client.post("/api/v1/auth/token", json={"login":"admin", "password":PASSWORD}).json()["access_token"]
    monkeypatch.delenv("ANALYSIS_MODE")
    with TestClient(create_app(os.environ["IV_TEST_DATABASE_URL"]), base_url="http://testserver") as disabled:
        response = disabled.post("/api/v1/inspections/preview", data={"equipment_id":equipment, "source":"CAMERA"},
                                 files={"image":("photo.png", image, "image/png")},
                                 headers={"Authorization":"Bearer " + token})
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "MODEL_UNAVAILABLE"


def test_photo_preview_limits_chunked_body(client, preview_upload):
    from app.presentation.uploads import MAX_MULTIPART_BYTES
    # No Content-Length: the limit must be enforced against the actual body.
    response = client.post("/api/v1/inspections/preview", content=iter([b"x" * (MAX_MULTIPART_BYTES + 1)]),
                           headers={**HEADERS, "Content-Type":"multipart/form-data; boundary=test"})
    assert response.status_code == 413 and response.json()["error"]["code"] == "IMAGE_TOO_LARGE"


def test_photo_preview_limits_file_bytes(client, preview_upload):
    from app.application.dtos.analysis import MAX_IMAGE_BYTES
    equipment, image = preview_upload
    content = image + b"x" * (MAX_IMAGE_BYTES + 1 - len(image))
    response = client.post("/api/v1/inspections/preview", data={"equipment_id":equipment, "source":"CAMERA"},
                           files={"image":("photo.png", content, "image/png")}, headers=HEADERS)
    assert response.status_code == 413 and response.json()["error"]["code"] == "IMAGE_TOO_LARGE"


def test_photo_preview_malformed_multipart(client, preview_upload):
    response = client.post("/api/v1/inspections/preview", content=b"not-a-boundary\r\n",
                           headers={**HEADERS, "Content-Type":"multipart/form-data; boundary=test"})
    assert response.status_code == 422 and response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_saved_inspection_survives_restart(client, preview_upload):
    from uuid import uuid4
    equipment, image = preview_upload
    headers = {**HEADERS, "Idempotency-Key":str(uuid4())}
    response = client.post("/api/v1/inspections", data={"equipment_id":equipment, "source":"CAMERA"},
                           files={"image":("photo.png", image, "image/png")}, headers=headers)
    assert response.status_code == 201
    result = response.json()
    assert result["created_at"].endswith("Z")
    assert result["analysis_source"] == "MOCK" and result["model_version"] is None
    assert result["inspection_id"] > 0 and result["photo_id"] > 0
    assert client.get(f"/api/v1/inspections/{result['inspection_id']}").json() == result
    assert client.get(f"/api/v1/photos/{result['photo_id']}").status_code == 200
    repeated = client.post("/api/v1/inspections", data={"equipment_id":equipment, "source":"CAMERA"},
                           files={"image":("another.png", image, "image/png")}, headers=headers)
    assert repeated.status_code == 201 and repeated.json() == result
    with TestClient(create_app(os.environ["IV_TEST_DATABASE_URL"], secure=False, origin="http://testserver"),
                    base_url="http://testserver") as restarted:
        admin(restarted)
        assert restarted.get(f"/api/v1/inspections/{result['inspection_id']}").json() == result
        assert restarted.get(f"/api/v1/photos/{result['photo_id']}").status_code == 200
        history = restarted.get(f"/api/v1/equipment/{equipment}/inspections").json()
        assert history["total"] == 1 and history["items"][0]["result"] == result


def test_inspection_replays_failure_and_detects_changed_request(client, preview_upload):
    from uuid import uuid4
    equipment, image = preview_upload
    headers = {**HEADERS, "Idempotency-Key":str(uuid4())}
    data = {"equipment_id":equipment, "source":"CAMERA"}
    failed = client.post("/api/v1/inspections", data=data, files={"image":("bad.jpg", b"\xff\xd8broken")}, headers=headers)
    assert failed.status_code == 422
    replay = client.post("/api/v1/inspections", data=data, files={"image":("bad.jpg", b"\xff\xd8broken")}, headers=headers)
    assert replay.status_code == 422 and replay.json() == failed.json()
    changed = client.post("/api/v1/inspections", data=data, files={"image":("good.png", image)}, headers=headers)
    assert changed.status_code == 409 and changed.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    history = client.get(f"/api/v1/equipment/{equipment}/inspections").json()
    assert history["total"] == 1 and history["items"][0]["processing_status"] == "FAILED"
    assert history["items"][0]["result"] is None


def test_inspections_and_photos_are_scoped(client, preview_upload):
    from uuid import uuid4
    equipment, image = preview_upload
    result = client.post("/api/v1/inspections", data={"equipment_id":equipment, "source":"CAMERA"},
                         files={"image":("photo.png", image)}, headers={**HEADERS, "Idempotency-Key":str(uuid4())}).json()
    other_workshop = client.post("/api/v1/workshops", json={"name":"Другой цех"}, headers=HEADERS).json()["id"]
    tokens = []
    for login, workshop in (("own", result["workshop_id"]), ("other", other_workshop)):
        assert client.post("/api/v1/users", json={"login":login, "password":PASSWORD, "full_name":login,
                           "role":"WORKER", "workshop_id":workshop}, headers=HEADERS).status_code == 201
        tokens.append(client.post("/api/v1/auth/token", json={"login":login, "password":PASSWORD}).json()["access_token"])
    client.cookies.clear()
    paths = [f"/api/v1/inspections/{result['inspection_id']}", f"/api/v1/photos/{result['photo_id']}",
             f"/api/v1/equipment/{equipment}/inspections"]
    for path in paths:
        assert client.get(path).status_code == 401
        assert client.get(path, headers={"Authorization":"Bearer " + tokens[0]}).status_code == 200
        forbidden = client.get(path, headers={"Authorization":"Bearer " + tokens[1]})
        missing = client.get(path.rsplit("/", 1)[0] + "/999999" if not path.endswith("/inspections")
                             else "/api/v1/equipment/999999/inspections", headers={"Authorization":"Bearer " + tokens[1]})
        assert forbidden.status_code == missing.status_code == 404
        assert forbidden.json() == missing.json()
    denied = client.post("/api/v1/inspections", data={"equipment_id":equipment, "source":"CAMERA"},
                         files={"image":("photo.png", image)},
                         headers={"Authorization":"Bearer " + tokens[1], "Idempotency-Key":str(uuid4())})
    assert denied.status_code == 404


def test_inspection_history_pagination_and_parallel_retries(client, preview_upload):
    from uuid import uuid4
    from concurrent.futures import ThreadPoolExecutor
    equipment, image = preview_upload
    token = client.post("/api/v1/auth/token", json={"login":"admin", "password":PASSWORD}).json()["access_token"]
    client.cookies.clear()
    headers = {"Authorization":"Bearer " + token, "Idempotency-Key":str(uuid4())}
    def create():
        return client.post("/api/v1/inspections", data={"equipment_id":equipment, "source":"GALLERY"},
                           files={"image":("photo.png", image)}, headers=headers)
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _:create(), range(4)))
    assert all(r.status_code in (201, 409) for r in responses)
    assert any(r.status_code == 201 for r in responses)
    assert all(r.json()["error"]["code"] == "REQUEST_IN_PROGRESS" for r in responses if r.status_code == 409)
    replay = create()
    assert replay.status_code == 201
    ids = [replay.json()["inspection_id"]]
    for _ in range(2):
        headers["Idempotency-Key"] = str(uuid4())
        ids.append(create().json()["inspection_id"])
    history = client.get(f"/api/v1/equipment/{equipment}/inspections?limit=1&offset=1", headers=headers)
    assert history.status_code == 200
    assert history.json()["total"] == 3 and history.json()["items"][0]["inspection_id"] == ids[1]
    assert client.get(f"/api/v1/equipment/{equipment}/inspections?limit=101", headers=headers).status_code == 422
    assert client.get(f"/api/v1/equipment/{equipment}/inspections?offset=-1", headers=headers).status_code == 422


def test_storage_failure_is_saved_without_fallback(client, preview_upload):
    from uuid import uuid4
    from pathlib import Path
    equipment, image = preview_upload
    root = Path(os.environ["PHOTO_ROOT"])
    root.rmdir()
    root.write_text("storage unavailable")
    headers = {**HEADERS, "Idempotency-Key":str(uuid4())}
    response = client.post("/api/v1/inspections", data={"equipment_id":equipment, "source":"CAMERA"},
                           files={"image":("photo.png", image)}, headers=headers)
    assert response.status_code == 503 and response.json()["error"]["code"] == "STORAGE_UNAVAILABLE"
    root.unlink()
    root.mkdir()
    replay = client.post("/api/v1/inspections", data={"equipment_id":equipment, "source":"CAMERA"},
                         files={"image":("photo.png", image)}, headers=headers)
    assert replay.status_code == 503 and replay.json() == response.json()
    assert not list(root.iterdir())


def test_interrupted_inspection_recovers_as_failed(client, preview_upload):
    from uuid import uuid4
    from sqlalchemy import update
    from app.infrastructure.inspections import PostgresInspectionRepository
    from app.infrastructure.models import Inspection
    equipment, _ = preview_upload
    engine = make_engine(os.environ["IV_TEST_DATABASE_URL"])
    factory = sessions(engine)
    record, _ = PostgresInspectionRepository(factory).reserve(equipment_id=equipment, workshop_id=1,
                         author_id=1, source="CAMERA", key=str(uuid4()), request_hash="a" * 64, storage_backend="local")
    assert client.get(f"/api/v1/inspections/{record.id}").status_code == 409
    with factory.begin() as db:
        db.execute(update(Inspection).where(Inspection.id == record.id).values(deadline=datetime.now(timezone.utc) - timedelta(seconds=1)))
    response = client.get(f"/api/v1/inspections/{record.id}")
    assert response.status_code == 503 and response.json()["error"]["code"] == "ANALYSIS_INTERRUPTED"
    with factory() as db:
        row = db.get(Inspection, record.id)
        assert row.processing_status == "FAILED" and row.cleanup_pending
    engine.dispose()


def test_saved_photo_is_normalized_and_survives_storage_selection_change(client, preview_upload, monkeypatch):
    from io import BytesIO
    from uuid import uuid4
    from PIL import Image
    equipment, _ = preview_upload
    content = BytesIO()
    exif = Image.Exif()
    exif[274] = 6
    with Image.new("RGB", (32, 24)) as image:
        image.save(content, format="JPEG", exif=exif)
    headers = {**HEADERS, "Idempotency-Key":str(uuid4())}
    response = client.post("/api/v1/inspections", data={"equipment_id":equipment, "source":"CAMERA"},
                           files={"image":("photo.jpg", content.getvalue())}, headers=headers)
    assert response.status_code == 201
    result = response.json()
    assert result["image"] == {"width":24, "height":32}
    monkeypatch.setenv("PHOTO_STORAGE", "nextcloud")
    monkeypatch.setenv("NEXTCLOUD_WEBDAV_URL", "https://unreachable.invalid/remote.php/dav/files/user/photos")
    monkeypatch.setenv("NEXTCLOUD_USERNAME", "user")
    monkeypatch.setenv("NEXTCLOUD_APP_PASSWORD", "test-app-password")
    with TestClient(create_app(os.environ["IV_TEST_DATABASE_URL"], secure=False, origin="http://testserver"),
                    base_url="http://testserver") as switched:
        admin(switched)
        photo = switched.get(f"/api/v1/photos/{result['photo_id']}")
        assert photo.status_code == 200 and photo.headers["content-type"] == "image/jpeg"
        assert photo.headers["cache-control"] == "no-store"
        with Image.open(BytesIO(photo.content)) as normalized:
            assert normalized.size == (24, 32) and not normalized.getexif()
        repeated = switched.post("/api/v1/inspections", data={"equipment_id":equipment, "source":"CAMERA"},
                                 files={"image":("photo.jpg", content.getvalue())}, headers=headers)
        assert repeated.status_code == 201 and repeated.json() == result


def test_saved_inspection_requires_key_and_browser_origin(client, preview_upload):
    equipment, image = preview_upload
    data, files = {"equipment_id":equipment, "source":"CAMERA"}, {"image":("photo.png", image)}
    response = client.post("/api/v1/inspections", data=data, files=files, headers=HEADERS)
    assert response.status_code == 422 and response.json()["error"]["code"] == "VALIDATION_ERROR"
    response = client.post("/api/v1/inspections", data=data, files=files, headers={"Authorization":"Basic invalid"})
    assert response.status_code == 403
    assert client.get(f"/api/v1/equipment/{equipment}/inspections").json()["total"] == 0
