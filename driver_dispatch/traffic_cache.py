from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


class JsonCache:
    def __init__(self, directory: Path):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)

    def _path(self, namespace: str, key: object) -> Path:
        digest = hashlib.sha256(json.dumps(key, sort_keys=True, default=str).encode()).hexdigest()
        return self.directory / f"{namespace}-{digest}.json"

    def get(self, namespace: str, key: object, max_age_minutes: int, allow_stale: bool = False):
        path = self._path(namespace, key)
        if not path.exists(): return None
        try:
            envelope = json.loads(path.read_text(encoding="utf-8"))
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(envelope["stored_at"])).total_seconds() / 60
            if age > max_age_minutes and not allow_stale: return None
            return envelope["value"], age, age > max_age_minutes
        except (ValueError, KeyError, OSError, json.JSONDecodeError):
            return None

    def set(self, namespace: str, key: object, value: object):
        payload = {"stored_at": datetime.now(timezone.utc).isoformat(), "value": value}
        self._path(namespace, key).write_text(json.dumps(payload, default=str), encoding="utf-8")

