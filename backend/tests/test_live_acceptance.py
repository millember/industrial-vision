"""Opt-in HTTP checks against a disposable loopback Docker stack, never production."""
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import urlsplit
from uuid import uuid4
import httpx
from PIL import Image
import pytest

pytestmark = pytest.mark.skipif(not os.getenv("IV_ACCEPTANCE_URL"), reason="Requires an explicitly prepared disposable loopback stack")


class LiveAPI:
    def __init__(self):
        self.base = os.environ["IV_ACCEPTANCE_URL"].rstrip("/")
        parsed = urlsplit(self.base)
        assert parsed.hostname in ("127.0.0.1", "localhost", "::1") and parsed.scheme == "http"
        assert parsed.path == "/industrial-vision", "Test the real installation prefix"
        self.settings = json.loads(Path(os.environ["IV_ACCEPTANCE_STATE_FILE"]).read_text())
        self.client = httpx.Client(headers={"Host":"pet.oppennec.ru"}, timeout=30, trust_env=False)
        self.tokens = {}

    def request(self, method, path, role=None, **kwargs):
        extra = kwargs.pop("headers", {})
        if role:
            if role not in self.tokens:
                result = self.request("POST", "/api/v1/auth/token", json={"login":"demo_" + role,"password":self.settings["password"]})
                assert result.status_code == 200
                self.tokens[role] = result.json()["access_token"]
            extra = {**extra,"Authorization":"Bearer " + self.tokens[role]}
        for _ in range(24):
            response = self.client.request(method, self.base + path, headers=extra, **kwargs)
            if response.status_code != 429:
                return response
            time.sleep(0.25)  # Respect the deployed gateway's 5 rps limit.
        raise AssertionError("Gateway rate limit did not recover")


@pytest.fixture
def live():
    api = LiveAPI()
    yield api
    api.client.close()


def test_live_workflow_through_gateway(live):
    if os.getenv("IV_ACCEPTANCE_PHASE", "workflow") != "workflow":
        pytest.skip("Run before restarting the backend container")
    demo = live.settings["demo"]
    for path in ("/docs", "/openapi.json", "/api/v1/users"):
        assert live.request("GET", path).status_code == 401
    html = live.request("GET", "/")
    assert html.status_code == 200
    script = re.search(r'src="(/industrial-vision/assets/[^\"]+\.js)"', html.text)
    assert script, "Built frontend must load its prefixed JavaScript"
    asset = live.client.get(live.base.removesuffix("/industrial-vision") + script[1])
    assert asset.status_code == 200 and "javascript" in asset.headers["content-type"]
    login = live.request("POST", "/api/v1/auth/login", json={"login":"acceptance_admin","password":live.settings["password"]},
                         headers={"Origin":"http://pet.oppennec.ru","X-IV-Client":"browser"})
    assert login.status_code == 200
    docs = live.request("GET", "/docs")
    assert docs.status_code == 200 and '"filter": true' in docs.text
    schema = live.request("GET", "/openapi.json")
    assert schema.status_code == 200
    assert schema.json()["servers"] == [{"url":"/industrial-vision"}]
    assert all(op["tags"] != ["default"] for item in schema.json()["paths"].values() for op in item.values())
    live.client.cookies.clear()
    assert live.request("GET", "/docs", "worker").status_code == 401
    photo = BytesIO()
    with Image.frombytes("RGB", (256,256), os.urandom(256 * 256 * 3)) as image:
        image.save(photo, format="PNG")
    content = photo.getvalue()
    assert len(content) > 65536
    equipment = demo["equipment"]["1"]
    fields = {"equipment_id":equipment,"source":"CAMERA"}
    preview = live.request("POST", "/api/v1/inspections/preview", "worker", data=fields, files={"image":("camera.png",content,"image/png")})
    assert preview.status_code == 200 and preview.json()["status"] == "UNKNOWN"
    # Non-upload JSON routes retain their smaller limit.
    assert live.request("POST", "/api/v1/auth/token", json={"login":"invalid", "password":"x" * 70000}).status_code == 413
    assert live.request("POST", "/api/v1/inspections/preview", "worker", content=b"x" * (10551296 + 1), headers={"Content-Type":"application/octet-stream"}).status_code == 413
    warning = demo["inspections"]["warning"]
    report_headers = {"Idempotency-Key":str(uuid4())}
    report = live.request("POST", f"/api/v1/inspections/{warning}/reports", "worker", json={}, headers=report_headers)
    assert report.status_code == 201
    assert live.request("POST", f"/api/v1/inspections/{warning}/reports", "worker", json={}, headers=report_headers).json() == report.json()
    notices = live.request("GET", "/api/v1/notifications", "master")
    assert notices.status_code == 200 and notices.json()["total"] == 1
    notification_id = notices.json()["items"][0]["id"]
    assert live.request("PATCH", f"/api/v1/notifications/{notification_id}", "master", json={"is_read":True}).json()["is_read"]
    repaired = live.request("POST", "/api/v1/inspections", "worker", data=fields, files={"image":("camera.png",content,"image/png")}, headers={"Idempotency-Key":str(uuid4())})
    assert repaired.status_code == 201 and repaired.json()["status"] == "UNKNOWN"
    inspection_id = repaired.json()["inspection_id"]
    verified = live.request("POST", f"/api/v1/inspections/{inspection_id}/reviews", "engineer",
        json={"decision":"CONFIRMED","status":"OK","comment":"Приёмка: проверено после ремонта","expected_review_id":None}, headers={"Idempotency-Key":str(uuid4())})
    assert verified.status_code == 201
    issue_id = report.json()["issue_id"]
    closed = live.request("POST", f"/api/v1/issues/{issue_id}/close", "master",
        json={"reason":"Приёмка: крепление проверено","verification_review_id":verified.json()["review_id"],"expected_report_id":report.json()["report_id"]}, headers={"Idempotency-Key":str(uuid4())})
    assert closed.status_code == 200
    assert live.request("GET", f"/api/v1/inspections/{inspection_id}", "foreign").status_code == 404
    saved_photo = live.request("GET", f"/api/v1/photos/{inspection_id}", "worker")
    assert saved_photo.status_code == 200
    result_file = Path(os.environ["IV_ACCEPTANCE_RESULT_FILE"])
    result_file.write_text(json.dumps({"inspection_id":inspection_id,"issue":closed.json(),"photo_sha256":hashlib.sha256(saved_photo.content).hexdigest()}))
    result_file.chmod(0o600)


def test_live_data_survives_container_restart(live):
    if os.getenv("IV_ACCEPTANCE_PHASE") != "restart":
        pytest.skip("Run after restarting the backend and database containers")
    result = json.loads(Path(os.environ["IV_ACCEPTANCE_RESULT_FILE"]).read_text())
    inspection = live.request("GET", f"/api/v1/inspections/{result['inspection_id']}", "worker")
    assert inspection.status_code == 200
    assert inspection.json()["status"] == "OK" and inspection.json()["original_result"]["status"] == "UNKNOWN"
    assert live.request("GET", f"/api/v1/issues/{result['issue']['issue_id']}", "worker").json() == result["issue"]
    photo = live.request("GET", f"/api/v1/photos/{result['inspection_id']}", "worker")
    assert photo.status_code == 200 and hashlib.sha256(photo.content).hexdigest() == result["photo_sha256"]
    assert live.request("GET", "/api/v1/notifications", "master").json()["items"][0]["is_read"]


def test_live_two_large_uploads_fit_declared_limits(live):
    from concurrent.futures import ThreadPoolExecutor
    if os.getenv("IV_ACCEPTANCE_PHASE", "workflow") != "workflow":
        pytest.skip("Upload resource check runs before restart")
    assert live.request("GET", "/api/v1/me", "worker").status_code == 200
    photo = BytesIO()
    with Image.frombytes("RGB", (1800,1700), os.urandom(1800 * 1700 * 3)) as image:
        image.save(photo, format="PNG")
    content = photo.getvalue()
    assert 8 * 1024 * 1024 < len(content) < 10 * 1024 * 1024
    def upload(_):
        return live.request("POST", "/api/v1/inspections/preview", "worker",
                            data={"equipment_id":live.settings["demo"]["equipment"]["1"],"source":"CAMERA"},
                            files={"image":("large.png",content,"image/png")})
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(upload, range(2)))
    assert [response.status_code for response in responses] == [200,200]
