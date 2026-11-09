
import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text, select
from app.main import create_app
from app.infrastructure.database import make_engine, sessions
from app.infrastructure.repository import Repository
from app.infrastructure.models import ApiKey, BrowserSession
from app.infrastructure.passwords import Passwords

PASSWORD = "Example-Test-Password-2026!"
HEADERS = {"Origin":"http://testserver","X-IV-Client":"browser"}

@pytest.fixture
def client():
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
    client.cookies.clear()
    headers={"Authorization":"Bearer "+key["key"]}
    assert client.get("/api/v1/health",headers=headers).status_code==200
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
