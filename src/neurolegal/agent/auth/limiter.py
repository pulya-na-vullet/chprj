"""In-memory sliding-window rate limiter.

One process, no new dependencies: a `dict[key, deque[timestamp]]`. Not shared
across workers — fine at current scale (single uvicorn process; a multi-worker
deploy is warned about at agent startup, see `api/app._warn_if_multiworker`).
The clock is injectable so tests don't need real sleeps.
"""

import time
from collections import deque
from collections.abc import Callable

#: Sweep stale keys once the map crosses this many entries. Bounds the
#: dict to the live working set instead of growing once per distinct key.
_SWEEP_THRESHOLD = 10_000


class RateLimiter:
    def __init__(self, clock: Callable[[], float] | None = None) -> None:
        self._clock = clock or time.monotonic
        self._hits: dict[str, deque[float]] = {}

    def allow(self, key: str, *, limit: int, window_seconds: float) -> bool:
        """Record a hit for `key` and return whether it's within budget.

        Only records the hit (advances state) when allowed — a rejected call
        doesn't itself count against the caller's future budget.
        """
        if len(self._hits) >= _SWEEP_THRESHOLD:
            self.sweep(window_seconds=window_seconds)
        now = self._clock()
        hits = self._hits.setdefault(key, deque())
        while hits and now - hits[0] >= window_seconds:
            hits.popleft()
        if len(hits) >= limit:
            return False
        hits.append(now)
        return True

    def sweep(self, *, window_seconds: float) -> None:
        """Drop keys whose window has fully aged out.

        `allow` only trims the front of a key's deque, never removes the key,
        so on a public login every distinct `login:email:<addr>` leaves a
        permanent (eventually empty) entry — a cheap slow memory-growth vector.
        Call periodically; keys reappear on the next hit.
        """
        now = self._clock()
        stale = [
            key for key, hits in self._hits.items() if not hits or now - hits[-1] >= window_seconds
        ]
        for key in stale:
            del self._hits[key]
