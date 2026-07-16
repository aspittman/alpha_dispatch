from __future__ import annotations

import hashlib
import json
import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from driver_dispatch.models import Event

log = logging.getLogger(__name__)


class SourceError(RuntimeError):
    pass


class EventSource(ABC):
    name = "base"

    @abstractmethod
    def collect(self, start: datetime, end: datetime) -> list[Event]: ...


class HttpEventSource(EventSource):
    def __init__(self, cache_dir: Path, timeout: float = 20, cache_ttl: int = 21600):
        self.cache_dir = cache_dir / self.name
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.cache_ttl = cache_ttl

    def _cache_path(self, url: str, params: dict) -> Path:
        key = hashlib.sha256((url + json.dumps(params, sort_keys=True)).encode()).hexdigest()
        return self.cache_dir / f"{key}.json"

    @retry(retry=retry_if_exception_type((httpx.HTTPError, SourceError)), stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8), reraise=True)
    def get_json(self, url: str, params: dict, headers: dict | None = None) -> dict:
        cache = self._cache_path(url, params)
        if cache.exists() and time.time() - cache.stat().st_mtime < self.cache_ttl:
            return json.loads(cache.read_text(encoding="utf-8"))
        response = httpx.get(url, params=params, headers=headers, timeout=self.timeout, follow_redirects=True)
        if response.status_code == 429:
            raise SourceError(f"{self.name} rate limit reached")
        response.raise_for_status()
        data = response.json()
        cache.write_text(json.dumps(data), encoding="utf-8")
        return data

