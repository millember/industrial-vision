import os
import re
from pathlib import Path
from urllib.parse import urlsplit
import httpx
from app.application.dtos.analysis import MAX_IMAGE_PIXELS
from app.application.ports.inspections import PhotoStorage
from app.domain.errors import AnalysisError

MAX_STORED_PHOTO_BYTES = MAX_IMAGE_PIXELS * 4 + 1024 * 1024


class LocalPhotoStorage:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{32}", key):
            raise AnalysisError("STORAGE_UNAVAILABLE", "Некорректный ключ фотографии")
        return self.root / key

    def put(self, key: str, content: bytes, media_type: str) -> None:
        try:
            with self._path(key).open("xb") as output:
                os.chmod(output.name, 0o600)
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
            descriptor = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        except OSError:
            raise AnalysisError("STORAGE_UNAVAILABLE", "Хранилище фотографий недоступно") from None

    def get(self, key: str) -> bytes:
        try:
            with self._path(key).open("rb") as source:
                content = source.read(MAX_STORED_PHOTO_BYTES + 1)
            if len(content) > MAX_STORED_PHOTO_BYTES:
                raise AnalysisError("STORAGE_UNAVAILABLE", "Некорректный размер сохранённой фотографии")
            return content
        except OSError:
            raise AnalysisError("STORAGE_UNAVAILABLE", "Сохранённая фотография недоступна") from None

    def delete(self, key: str) -> None:
        try:
            self._path(key).unlink(missing_ok=True)
        except OSError:
            raise AnalysisError("STORAGE_UNAVAILABLE", "Не удалось удалить фотографию") from None


class NextcloudPhotoStorage:
    def __init__(self, url: str, username: str, password: str, *, transport: httpx.BaseTransport | None = None):
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.query or parsed.fragment:
            raise ValueError("NEXTCLOUD_WEBDAV_URL must be an HTTPS folder URL without credentials, query or fragment")
        if not username or not password:
            raise ValueError("Nextcloud requires NEXTCLOUD_USERNAME and NEXTCLOUD_APP_PASSWORD")
        self.url, self._auth, self._transport = url.rstrip("/") + "/", (username, password), transport

    def _url(self, key: str) -> str:
        if not re.fullmatch(r"[a-f0-9]{32}", key):
            raise AnalysisError("STORAGE_UNAVAILABLE", "Некорректный ключ фотографии")
        return self.url + key

    def put(self, key: str, content: bytes, media_type: str) -> None:
        self._request("PUT", key, (201, 204), content=content, headers={"Content-Type":media_type})

    def get(self, key: str) -> bytes:
        return self._request("GET", key, (200,))

    def delete(self, key: str) -> None:
        self._request("DELETE", key, (204, 404))

    def _request(self, method: str, key: str, statuses: tuple[int, ...], **kwargs) -> bytes:
        try:
            with httpx.Client(auth=self._auth, timeout=httpx.Timeout(30, connect=10), follow_redirects=False,
                              trust_env=False, transport=self._transport) as client:
                with client.stream(method, self._url(key), **kwargs) as response:
                    if response.status_code not in statuses:
                        raise AnalysisError("STORAGE_UNAVAILABLE", "Nextcloud недоступен или отказал в операции")
                    content = bytearray()
                    if method == "GET":
                        for chunk in response.iter_bytes():
                            if len(content) + len(chunk) > MAX_STORED_PHOTO_BYTES:
                                raise AnalysisError("STORAGE_UNAVAILABLE", "Некорректный размер сохранённой фотографии")
                            content.extend(chunk)
                    return bytes(content)
        except httpx.HTTPError:
            raise AnalysisError("STORAGE_UNAVAILABLE", "Не удалось связаться с Nextcloud") from None


def photo_storages() -> tuple[str, dict[str, PhotoStorage]]:
    selected = os.getenv("PHOTO_STORAGE", "local")
    if selected not in ("local", "nextcloud"):
        raise ValueError("PHOTO_STORAGE must be local or nextcloud")
    storages: dict[str, PhotoStorage] = {"local":LocalPhotoStorage(Path(os.getenv("PHOTO_ROOT", "var/photos")))}
    url = os.getenv("NEXTCLOUD_WEBDAV_URL", "")
    if url or selected == "nextcloud":
        storages["nextcloud"] = NextcloudPhotoStorage(url, os.getenv("NEXTCLOUD_USERNAME", ""), os.getenv("NEXTCLOUD_APP_PASSWORD", ""))
    return selected, storages
