import json
import logging
import os
import re
import signal
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from dotenv import load_dotenv

from app import homebox as hb_module
from app import notifier, renderer

log = logging.getLogger(__name__)

_config: dict = {}
_homebox: hb_module.HomeboxClient | None = None

SECURITY_HEADERS = [
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Referrer-Policy", "no-referrer"),
    ("Strict-Transport-Security", "max-age=63072000; includeSubDomains"),
    (
        "Content-Security-Policy",
        "default-src 'self'; "
        "script-src 'unsafe-inline'; "
        "style-src 'unsafe-inline'; "
        "img-src 'self'; "
        "frame-ancestors 'none';",
    ),
]

_ASSET_ID_RE = re.compile(r"^[A-Za-z0-9\-_]{1,64}$")


def _load_config(env_path: str) -> dict:
    load_dotenv(env_path)

    def _parse_urls(key: str) -> list[str]:
        val = os.getenv(key, "")
        return [u.strip() for u in val.split(",") if u.strip()]

    def _parse_tag_templates() -> dict:
        templates = {}
        n = 1
        while True:
            tag = os.getenv(f"TEMPLATE_{n}_TAG")
            if not tag:
                break
            templates[tag] = {
                "file": os.getenv(f"TEMPLATE_{n}_FILE", "item.html"),
                "notify": _parse_urls(f"TEMPLATE_{n}_NOTIFY"),
                "notify_title": os.getenv(f"TEMPLATE_{n}_NOTIFY_TITLE", ""),
                "notify_body": os.getenv(f"TEMPLATE_{n}_NOTIFY_BODY", ""),
            }
            n += 1
        templates["_default"] = {
            "file": os.getenv("TEMPLATE_DEFAULT", "item.html"),
            "notify": _parse_urls("TEMPLATE_DEFAULT_NOTIFY"),
            "notify_title": os.getenv("TEMPLATE_DEFAULT_NOTIFY_TITLE", ""),
            "notify_body": os.getenv("TEMPLATE_DEFAULT_NOTIFY_BODY", ""),
        }
        return templates

    def _parse_contacts() -> list[dict]:
        contacts = []
        n = 1
        while True:
            ctype = os.getenv(f"CONTACT_{n}_TYPE")
            if not ctype:
                break
            contacts.append({
                "type": ctype,
                "label": os.getenv(f"CONTACT_{n}_LABEL", ""),
                "value": os.getenv(f"CONTACT_{n}_VALUE", ""),
            })
            n += 1
        return contacts

    return {
        "homebox": {
            "url": os.environ["HOMEBOX_URL"],
            "api_key": os.environ["HOMEBOX_API_KEY"],
        },
        "tag_templates": _parse_tag_templates(),
        "contacts": _parse_contacts(),
        "server": {
            "host": os.getenv("SERVER_HOST", "127.0.0.1"),
            "port": int(os.getenv("SERVER_PORT", "8080")),
        },
        "logging": {
            "level": os.getenv("LOG_LEVEL", "INFO"),
        },
    }


def _resolve_template(tags: list[dict], tag_templates: dict) -> dict:
    for tag in tags:
        name = tag.get("name", "")
        for key, entry in tag_templates.items():
            if key == "_default":
                continue
            if name.lower() == key.lower():
                return entry
    return tag_templates.get("_default", {"file": "item.html", "notify": []})


class LandingHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # suppress default access log; we write our own

    def _send_response(self, code: int, content_type: str, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for name, value in SECURITY_HEADERS:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, code: int, html: str) -> None:
        self._send_response(code, "text/html; charset=utf-8", html.encode("utf-8"))

    def do_GET(self):
        start = time.monotonic()
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        status = 200

        try:
            if path == "/health":
                self._send_response(200, "text/plain", b"OK")
                status = 200

            elif path == "/landing":
                status = self._handle_landing(parsed.query)

            elif path.startswith("/a/"):
                # When running without nginx, handle QR code paths directly
                redirect_url = "/landing?ref=" + urllib.parse.quote(path, safe="/")
                self.send_response(302)
                self.send_header("Location", redirect_url)
                self.end_headers()
                status = 302

            elif path.startswith("/landing/photo/"):
                status = self._handle_photo(path)

            else:
                self._send_html(404, "<h1>Not found</h1>")
                status = 404

        except Exception:
            log.exception("Unhandled error for %s %s", self.command, self.path)
            self._send_html(500, "<h1>Internal server error</h1>")
            status = 500

        elapsed = (time.monotonic() - start) * 1000
        log.info("%s %s %d %.1fms", self.command, self.path, status, elapsed)

    def _handle_landing(self, query: str) -> int:
        params = urllib.parse.parse_qs(query)
        ref = params.get("ref", [""])[0]

        match = re.search(r"/a/([^/?#]+)", ref)
        asset_id = match.group(1) if match else None

        contacts = _config.get("contacts", [])

        not_found_contacts = [c for c in contacts if c["type"] == "email"][:1]

        if not asset_id or not _ASSET_ID_RE.match(asset_id):
            html = renderer.render("not_found.html", renderer.build_not_found_context(), not_found_contacts)
            self._send_html(404, html)
            return 404

        try:
            item = _homebox.get_item_by_asset_id(asset_id)
        except Exception:
            log.exception("Homebox lookup failed for asset %s", asset_id)
            item = None

        if item is None:
            html = renderer.render("not_found.html", renderer.build_not_found_context(), not_found_contacts)
            self._send_html(404, html)
            return 404

        tag_templates = _config.get("tag_templates", {"_default": {"file": "item.html", "notify": []}})
        tpl_entry = _resolve_template(item.get("tags") or [], tag_templates)
        template_name = tpl_entry["file"]
        notif_urls = tpl_entry["notify"]
        item_name = item.get("name", "unknown item")
        item_description = item.get("description", "")

        xff = self.headers.get("X-Forwarded-For", "")
        ip = xff.split(",")[0].strip() if xff else (self.headers.get("X-Real-IP") or self.client_address[0])

        _default_titles = {"plant.html": "🌿 Plant scanned"}
        _default_bodies = {"plant.html": "{name} was scanned by a visitor from {ip}"}
        title_tpl = tpl_entry.get("notify_title") or _default_titles.get(template_name, "📦 Lost item found")
        body_tpl = tpl_entry.get("notify_body") or _default_bodies.get(template_name, "{name} was scanned from {ip}")
        notifier.notify(
            notif_urls,
            title_tpl.format(name=item_name, ip=ip, description=item_description),
            body_tpl.format(name=item_name, ip=ip, description=item_description),
        )
        log.info("Notification fired for %s (%d url(s))", item_name, len(notif_urls))

        if template_name == "plant.html":
            ctx = renderer.build_plant_context(item)
        else:
            ctx = renderer.build_item_context(item, asset_id=asset_id)

        html = renderer.render(template_name, ctx, contacts)
        self._send_html(200, html)
        return 200

    def _handle_photo(self, path: str) -> int:
        parts = path.split("/")
        # /landing/photo/{item_uuid}/{attachment_id}
        if len(parts) != 5:
            self._send_html(404, "<h1>Not found</h1>")
            return 404

        item_uuid = parts[3]
        attachment_id = parts[4]

        try:
            data, content_type = _homebox.get_photo(item_uuid, attachment_id)
        except Exception:
            log.exception("Photo proxy error for %s/%s", item_uuid, attachment_id)
            self._send_response(502, "text/plain", b"Photo unavailable")
            return 502

        self._send_response(200, content_type, data)
        return 200


def _setup_logging(level_name: str) -> None:
    level = getattr(logging, level_name.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


def main():
    global _config, _homebox

    env_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        ".env",
    )
    _config = _load_config(env_path)

    log_cfg = _config.get("logging", {})
    _setup_logging(log_cfg.get("level", "INFO"))

    hb_cfg = _config["homebox"]
    _homebox = hb_module.HomeboxClient(
        url=hb_cfg["url"],
        api_key=hb_cfg["api_key"],
    )

    srv_cfg = _config.get("server", {})
    host = srv_cfg.get("host", "127.0.0.1")
    port = int(srv_cfg.get("port", 8080))

    server = ThreadingHTTPServer((host, port), LandingHandler)

    tag_templates = _config.get("tag_templates", {})
    contacts = _config.get("contacts", [])
    log.info("Homebox URL : %s", hb_cfg["url"])
    log.info("Listening   : %s:%d", host, port)
    log.info("Log level   : %s", log_cfg.get("level", "INFO"))
    log.info("Tag templates: %s", ", ".join(
        f"{k}→{e['file']}({'notify' if e['notify'] else 'no notify'})"
        for k, e in tag_templates.items()
    ))
    log.info("Contacts    : %d configured", len(contacts))

    def _sigterm(signum, frame):
        log.info("Shutting down (SIGTERM)")
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, _sigterm)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Shutting down (KeyboardInterrupt)")
        server.shutdown()


if __name__ == "__main__":
    main()
