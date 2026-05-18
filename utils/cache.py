"""Cache in-memory semplice con TTL"""

import time
from typing import Any, Optional


class SimpleCache:
    def __init__(self, ttl: int = 300):
        self.ttl = ttl
        self._store: dict[str, tuple[Any, float]] = {}

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, ts = entry
        if time.time() - ts > self.ttl:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any):
        self._store[key] = (value, time.time())

    def delete(self, key: str):
        self._store.pop(key, None)

    def clear(self):
        self._store.clear()

    def cleanup(self):
        """Rimuovi le entry scadute"""
        now = time.time()
        expired = [k for k, (_, ts) in self._store.items() if now - ts > self.ttl]
        for k in expired:
            del self._store[k]
