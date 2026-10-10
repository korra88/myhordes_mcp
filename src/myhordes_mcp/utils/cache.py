"""In-memory TTL cache with single-flight fetches.

Concurrent callers asking for the same key while a fetch is in progress await
that same fetch instead of starting their own, so N simultaneous tool calls
cost one upstream request. Results stay cached for `ttl` seconds afterwards.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable, Hashable
from typing import Any


class TTLCache:
    def __init__(self, ttl: float, *, cache_if: Callable[[Any], bool] | None = None):
        """
        Args:
            ttl: Seconds a result stays fresh. 0 disables caching; concurrent
                 calls are still coalesced into one fetch.
            cache_if: Predicate deciding whether a result is stored (e.g. skip
                      error results so the next call retries).
        """
        self.ttl = ttl
        self._cache_if = cache_if or (lambda _: True)
        self._store: dict[Hashable, tuple[float, Any]] = {}
        self._inflight: dict[Hashable, asyncio.Task] = {}

    async def get(self, key: Hashable, fetch: Callable[[], Awaitable[Any]]) -> Any:
        hit = self._store.get(key)
        if hit is not None and time.monotonic() - hit[0] < self.ttl:
            return hit[1]
        task = self._inflight.get(key)
        if task is None:
            task = asyncio.ensure_future(self._run(key, fetch))
            self._inflight[key] = task
        # shield: a cancelled caller must not cancel the fetch others wait on
        return await asyncio.shield(task)

    async def _run(self, key: Hashable, fetch: Callable[[], Awaitable[Any]]) -> Any:
        try:
            value = await fetch()
            if self.ttl > 0 and self._cache_if(value):
                now = time.monotonic()
                self._store = {k: v for k, v in self._store.items() if now - v[0] < self.ttl}
                self._store[key] = (now, value)
            return value
        finally:
            del self._inflight[key]

    def clear(self) -> None:
        self._store.clear()
