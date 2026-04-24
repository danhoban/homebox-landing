import logging
import threading
import urllib.parse

import requests

log = logging.getLogger(__name__)

_photo_cache: dict[str, tuple[bytes, str]] = {}
_cache_lock = threading.Lock()


class HomeboxClient:
    def __init__(self, url: str, username: str, password: str):
        self._base = url.rstrip("/")
        self._username = username
        self._password = password
        self._token: str | None = None
        self._lock = threading.Lock()

    def _login(self) -> None:
        log.debug("Authenticating with Homebox")
        resp = requests.post(
            f"{self._base}/api/v1/users/login",
            data={"username": self._username, "password": self._password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10,
        )
        resp.raise_for_status()
        token = resp.json()["token"]
        self._token = token if token.startswith("Bearer ") else token

    def _auth_headers(self) -> dict[str, str]:
        token = self._token
        if token and token.startswith("Bearer "):
            return {"Authorization": token}
        return {"Authorization": f"Bearer {token}"}

    def _get(self, path: str, **kwargs) -> requests.Response:
        with self._lock:
            if self._token is None:
                self._login()

        resp = requests.get(
            f"{self._base}{path}",
            headers=self._auth_headers(),
            timeout=10,
            **kwargs,
        )

        if resp.status_code == 401:
            log.debug("Got 401, re-authenticating")
            with self._lock:
                self._token = None
                self._login()
            resp = requests.get(
                f"{self._base}{path}",
                headers=self._auth_headers(),
                timeout=10,
                **kwargs,
            )
            if resp.status_code == 401:
                raise PermissionError("Homebox authentication failed after retry")

        return resp

    def get_item_by_asset_id(self, asset_id: str) -> dict | None:
        log.info("Asset lookup: GET /api/v1/assets/%s", asset_id)
        resp = self._get(f"/api/v1/assets/{asset_id}")
        if 400 <= resp.status_code < 500:
            return None
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items") or []
        log.info("Asset lookup returned %d item(s)", len(items))
        if not items:
            return None
        if len(items) > 1:
            raise ValueError(f"Asset ID {asset_id!r} matched {len(items)} items — expected exactly 1")
        item = items[0]
        log.info("Matched item: %s (id=%s)", item.get("name"), item.get("id"))
        return self.get_item(item["id"])

    def get_item(self, uuid: str) -> dict:
        log.debug("Fetching item: %s", uuid)
        resp = self._get(f"/api/v1/items/{uuid}")
        resp.raise_for_status()
        return resp.json()

    def get_photo(self, item_uuid: str, attachment_id: str) -> tuple[bytes, str]:
        with _cache_lock:
            if attachment_id in _photo_cache:
                return _photo_cache[attachment_id]

        log.debug("Fetching photo %s for item %s", attachment_id, item_uuid)
        resp = self._get(f"/api/v1/items/{item_uuid}/attachments/{attachment_id}")
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "image/jpeg")
        result = (resp.content, content_type)

        with _cache_lock:
            _photo_cache[attachment_id] = result

        return result
