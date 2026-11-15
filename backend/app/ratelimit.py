"""
Sliding-window per-IP rate limiter.
Injectable clock for tests.
"""
from __future__ import annotations

import time
from collections import deque
from typing import Callable

_ClockFn = Callable[[], float]


class RateLimiter:
    """
    Token-bucket sliding window: max `limit` requests per `window_s` seconds.
    Thread-safe via GIL (single-process).
    """

    def __init__(
        self,
        limit: int = 5,
        window_s: int = 60,
        clock: _ClockFn | None = None,
    ) -> None:
        self._limit = limit
        self._window_s = window_s
        self._clock: _ClockFn = clock or time.monotonic
        # ip -> deque of timestamps
        self._windows: dict[str, deque[float]] = {}

    def _evict_expired(self, ip: str, now: float) -> None:
        dq = self._windows.get(ip)
        if dq is None:
            return
        cutoff = now - self._window_s
        while dq and dq[0] <= cutoff:
            dq.popleft()
        if not dq:
            del self._windows[ip]

    def check(self, ip: str) -> tuple[bool, int]:
        """
        Returns (allowed, retry_after_s).
        retry_after_s is 0 when allowed.
        """
        now = self._clock()
        self._evict_expired(ip, now)
        dq = self._windows.get(ip, deque())

        if len(dq) < self._limit:
            dq.append(now)
            self._windows[ip] = dq
            return True, 0

        # Over limit — when does the oldest entry expire?
        oldest = dq[0]
        retry_after = int(oldest + self._window_s - now) + 1
        return False, max(1, retry_after)

    def evict_all_expired(self) -> None:
        """Housekeeping — call periodically to bound memory."""
        now = self._clock()
        for ip in list(self._windows.keys()):
            self._evict_expired(ip, now)


def get_client_ip(request_scope: dict, trusted_proxies: list[str] | None = None) -> str:
    """
    Extract client IP from ASGI scope.
    Only trust X-Forwarded-For if the direct peer is in trusted_proxies.
    """
    client = request_scope.get("client")
    peer_ip: str = client[0] if client else "unknown"

    if trusted_proxies and peer_ip in trusted_proxies:
        # Find rightmost untrusted hop in X-Forwarded-For
        headers = dict(request_scope.get("headers", []))
        xff = headers.get(b"x-forwarded-for", b"").decode()
        if xff:
            hops = [h.strip() for h in xff.split(",")]
            # Walk right-to-left; first hop not in trusted_proxies is the client
            for hop in reversed(hops):
                if hop not in trusted_proxies:
                    return hop
    return peer_ip
