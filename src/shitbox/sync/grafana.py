"""Grafana annotation client for driving events."""

import threading
from pathlib import Path
from typing import Optional, Tuple

import requests

from shitbox.events.detector import Event
from shitbox.utils.config import GrafanaConfig
from shitbox.utils.logging import get_logger

log = get_logger(__name__)


class GrafanaAnnotator:
    """Posts annotations to Grafana when driving events are detected."""

    def __init__(self, config: GrafanaConfig, captures_dir: str = "") -> None:
        self._config = config
        self._captures_dir = captures_dir
        self._url = config.url.rstrip("/") + "/api/annotations"
        self._headers = {"Content-Type": "application/json"}
        self._auth: Optional[Tuple[str, str]] = None

        if config.username and config.password_file:
            try:
                password = Path(config.password_file).read_text().strip()
            except OSError as e:
                log.warning(
                    "grafana_password_file_unreadable",
                    path=config.password_file,
                    error=str(e),
                )
                password = ""
            if password:
                self._auth = (config.username, password)
            else:
                log.warning("grafana_password_empty", path=config.password_file)

    def annotate_event(self, event: Event, video_path: Optional[Path] = None) -> None:
        """Post an annotation for a driving event in a background thread."""
        text = (
            f"{event.event_type.value} \u2014 peak {event.peak_value:.2f}g, "
            f"{event.duration:.1f}s"
        )

        if video_path and self._config.video_base_url and self._captures_dir:
            try:
                relative = video_path.relative_to(self._captures_dir)
                base = self._config.video_base_url.rstrip("/")
                url = f"{base}/{relative}"
                text += f'\n<a href="{url}">Video</a>'
            except ValueError:
                pass

        payload = {
            "time": int(event.start_time * 1000),
            "timeEnd": int(event.end_time * 1000),
            "tags": ["shitbox", event.event_type.value],
            "text": text,
        }

        t = threading.Thread(target=self._post_annotation, args=(payload,), daemon=True)
        t.start()

    def _post_annotation(self, payload: dict) -> None:
        """POST annotation to Grafana API."""
        try:
            resp = requests.post(
                self._url,
                json=payload,
                headers=self._headers,
                auth=self._auth,
                timeout=self._config.timeout_seconds,
            )
            if resp.ok:
                log.info("grafana_annotation_posted", tags=payload.get("tags"))
            else:
                log.warning(
                    "grafana_annotation_failed",
                    status=resp.status_code,
                    body=resp.text[:200],
                )
        except Exception as e:
            log.warning("grafana_annotation_error", error=str(e))
