"""Small HTTP client with an on-disk JSON cache, so rebuilding a booklet is cheap
and polite to the free services it uses (Nominatim, Overpass, Open-Meteo)."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import httpx

from paper_phone import __version__


class OfflineError(RuntimeError):
    """Raised when a request is needed but the client is offline and nothing is cached."""


class Http:
    def __init__(self, cache_dir: Path, *, offline: bool = False, contact: str | None = None):
        self.cache_dir = cache_dir / "http"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.offline = offline
        agent = f"paper-phone/{__version__} (printable pocket booklet)"
        if contact:
            agent += f" contact: {contact}"
        self.client = httpx.Client(
            headers={"User-Agent": agent}, timeout=httpx.Timeout(30.0, read=200.0)
        )
        self._last_hit: dict[str, float] = {}

    def _key(self, *parts: object) -> Path:
        digest = hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()
        return self.cache_dir / f"{digest[:40]}.json"

    def _cached(self, path: Path, ttl: float) -> Any | None:
        if not path.exists():
            return None
        if not self.offline and time.time() - path.stat().st_mtime > ttl:
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def _throttle(self, host: str, min_interval: float) -> None:
        wait = self._last_hit.get(host, 0) + min_interval - time.time()
        if wait > 0:
            time.sleep(wait)
        self._last_hit[host] = time.time()

    def get_json(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        *,
        ttl: float = 3600,
        min_interval: float = 0.0,
    ) -> Any:
        path = self._key("GET", url, params)
        if (hit := self._cached(path, ttl)) is not None:
            return hit
        if self.offline:
            raise OfflineError(url)
        self._throttle(httpx.URL(url).host, min_interval)
        response = self.client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        path.write_text(json.dumps(data), encoding="utf-8")
        return data

    def post_json(self, urls: list[str], data: dict[str, str], *, ttl: float) -> Any:
        """POST to the first mirror that answers (Overpass has several)."""
        path = self._key("POST", data)
        if (hit := self._cached(path, ttl)) is not None:
            return hit
        if self.offline:
            raise OfflineError(urls[0])
        errors: list[str] = []
        for url in urls:
            try:
                response = self.client.post(url, data=data)
                if response.status_code in (429, 502, 503, 504):
                    errors.append(f"{url}: HTTP {response.status_code}")
                    continue
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, json.JSONDecodeError) as exc:
                errors.append(f"{url}: {exc}")
                continue
            path.write_text(json.dumps(payload), encoding="utf-8")
            return payload
        raise RuntimeError("All mirrors failed: " + "; ".join(errors))

    def get_text(self, url: str, *, ttl: float = 900) -> str:
        path = self._key("TEXT", url)
        if path.exists() and (self.offline or time.time() - path.stat().st_mtime < ttl):
            return json.loads(path.read_text(encoding="utf-8"))
        if self.offline:
            raise OfflineError(url)
        response = self.client.get(url, follow_redirects=True)
        response.raise_for_status()
        path.write_text(json.dumps(response.text), encoding="utf-8")
        return response.text
