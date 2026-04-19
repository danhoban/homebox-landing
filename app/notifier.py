import apprise
import threading
import logging

log = logging.getLogger(__name__)


def notify(urls: list[str], title: str, body: str) -> None:
    """Fire notifications in a background thread. Never raises."""
    def _send():
        try:
            ap = apprise.Apprise()
            for url in urls:
                ap.add(url)
            ap.notify(title=title, body=body)
        except Exception as e:
            log.warning("Notification failed: %s", e)
    threading.Thread(target=_send, daemon=True).start()
