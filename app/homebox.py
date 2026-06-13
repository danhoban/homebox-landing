import logging
import threading

import requests

log = logging.getLogger(__name__)

_photo_cache: dict[str, tuple[bytes, str]] = {}
_cache_lock = threading.Lock()


class HomeboxClient:
    def __init__(self, url: str, api_key: str):
        self._base = url.rstrip("/")
        self._api_key = api_key

    def _get(self, path: str, **kwargs) -> requests.Response:
        return requests.get(
            f"{self._base}{path}",
            headers={"Authorization": f"Bearer {self._api_key}"},
            timeout=10,
            **kwargs,
        )

    def get_item_by_asset_id(self, asset_id: str) -> dict | None:
        log.info("Asset lookup: GET /api/v1/assets/%s", asset_id)
        resp = self._get(f"/api/v1/assets/{asset_id}")
        if not resp.ok:
            return None
        data = resp.json()
        items = data.get("items") or []
        log.info("Asset lookup returned %d item(s)", len(items))
        if not items:
            return None
        if len(items) > 1:
            log.warning("Asset ID %r matched %d items — using first", asset_id, len(items))
        item = items[0]
        log.info("Matched item: %s (id=%s)", item.get("name"), item.get("id"))
        return self.get_item(item["id"])

    def get_item(self, uuid: str) -> dict:
        log.debug("Fetching entity: %s", uuid)
        resp = self._get(f"/api/v1/entities/{uuid}")
        resp.raise_for_status()
        return resp.json()

    def get_photo(self, item_uuid: str, attachment_id: str) -> tuple[bytes, str]:
        with _cache_lock:
            if attachment_id in _photo_cache:
                return _photo_cache[attachment_id]

        log.debug("Fetching photo %s for entity %s", attachment_id, item_uuid)
        resp = self._get(f"/api/v1/entities/{item_uuid}/attachments/{attachment_id}")
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "image/jpeg")
        result = (resp.content, content_type)

        with _cache_lock:
            _photo_cache[attachment_id] = result

        return result
