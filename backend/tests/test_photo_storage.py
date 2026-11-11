import hashlib
from pathlib import Path
from uuid import uuid4
import httpx
import pytest
from app.domain.errors import AnalysisError
from app.infrastructure.photo_storage import LocalPhotoStorage, NextcloudPhotoStorage, photo_storages


def test_local_storage_round_trip_and_private_permissions(tmp_path):
    storage = LocalPhotoStorage(tmp_path / "photos")
    key = uuid4().hex
    storage.put(key, b"photo", "image/png")
    assert storage.get(key) == b"photo"
    assert (tmp_path / "photos" / key).stat().st_mode & 0o777 == 0o600
    storage.delete(key)
    storage.delete(key)
    with pytest.raises(AnalysisError):
        storage.get(key)


def test_storage_rejects_client_paths(tmp_path):
    storage = LocalPhotoStorage(tmp_path / "photos")
    with pytest.raises(AnalysisError):
        storage.put("../outside", b"x", "image/png")
    assert not (tmp_path / "outside").exists()


def test_nextcloud_webdav_round_trip():
    objects = {}
    def handler(request):
        assert request.url.scheme == "https"
        assert request.headers["Authorization"].startswith("Basic ")
        key = request.url.path.rsplit("/", 1)[1]
        if request.method == "PUT":
            objects[key] = request.content
            return httpx.Response(201)
        if request.method == "GET":
            return httpx.Response(200, content=objects[key])
        objects.pop(key, None)
        return httpx.Response(204)
    storage = NextcloudPhotoStorage("https://cloud.example/remote.php/dav/files/user/photos", "user", "app-password",
                                    transport=httpx.MockTransport(handler))
    key = uuid4().hex
    storage.put(key, b"normalized-photo", "image/png")
    assert storage.get(key) == b"normalized-photo"
    storage.delete(key)
    assert not objects


@pytest.mark.parametrize("status", [301, 401, 404, 500])
def test_nextcloud_rejects_errors_and_redirects(status):
    def handler(request):
        return httpx.Response(status, headers={"Location":"https://other.example/"})
    storage = NextcloudPhotoStorage("https://cloud.example/photos", "user", "secret", transport=httpx.MockTransport(handler))
    with pytest.raises(AnalysisError) as error:
        storage.put(uuid4().hex, b"photo", "image/png")
    assert error.value.code == "STORAGE_UNAVAILABLE" and "secret" not in str(error.value)


def test_storage_configuration_defaults_to_local(monkeypatch, tmp_path):
    monkeypatch.delenv("PHOTO_STORAGE", raising=False)
    monkeypatch.delenv("NEXTCLOUD_WEBDAV_URL", raising=False)
    monkeypatch.setenv("PHOTO_ROOT", str(tmp_path / "photos"))
    selected, storages = photo_storages()
    assert selected == "local" and set(storages) == {"local"}
    monkeypatch.setenv("PHOTO_STORAGE", "nextcloud")
    with pytest.raises(ValueError):
        photo_storages()
