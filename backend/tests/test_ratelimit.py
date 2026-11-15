"""Tests for ratelimit: sliding window, retry-after, proxy parsing."""
from __future__ import annotations

import pytest
from app.ratelimit import RateLimiter, get_client_ip
from tests.conftest import FakeClock


class TestRateLimiter:
    def test_allows_up_to_limit(self, fake_clock: FakeClock) -> None:
        limiter = RateLimiter(limit=5, window_s=60, clock=fake_clock)
        for _ in range(5):
            allowed, retry_after = limiter.check("1.2.3.4")
            assert allowed
            assert retry_after == 0

    def test_6th_request_blocked_with_retry_after(self, fake_clock: FakeClock) -> None:
        limiter = RateLimiter(limit=5, window_s=60, clock=fake_clock)
        for _ in range(5):
            limiter.check("1.2.3.4")
            fake_clock.advance(1.0)

        # 6th request at t=1005 (first was at t=1000)
        allowed, retry_after = limiter.check("1.2.3.4")
        assert not allowed
        # First request was at 1000, window is 60 -> expires at 1060.
        # Current time is 1005 -> retry_after should be approx 56s
        assert 50 <= retry_after <= 60

    def test_window_slides(self, fake_clock: FakeClock) -> None:
        limiter = RateLimiter(limit=2, window_s=10, clock=fake_clock)
        assert limiter.check("1.1.1.1")[0]  # t=1000
        fake_clock.advance(5.0)
        assert limiter.check("1.1.1.1")[0]  # t=1005
        assert not limiter.check("1.1.1.1")[0]  # blocked at t=1005

        # Advance past first request
        fake_clock.advance(6.0)  # t=1011 (first request expired at 1010)
        allowed, _ = limiter.check("1.1.1.1")
        assert allowed

    def test_different_ips_independent(self, fake_clock: FakeClock) -> None:
        limiter = RateLimiter(limit=1, window_s=60, clock=fake_clock)
        assert limiter.check("1.1.1.1")[0]
        assert not limiter.check("1.1.1.1")[0]

        # Different IP allowed
        assert limiter.check("2.2.2.2")[0]


class TestClientIPExtraction:
    def test_direct_socket_peer(self) -> None:
        scope = {
            "client": ("203.0.113.195", 54321),
            "headers": [],
        }
        ip = get_client_ip(scope, trusted_proxies=[])
        assert ip == "203.0.113.195"

    def test_spoofed_xff_ignored_without_trusted_proxy(self) -> None:
        scope = {
            "client": ("203.0.113.195", 54321),
            "headers": [(b"x-forwarded-for", b"198.51.100.1")],
        }
        ip = get_client_ip(scope, trusted_proxies=[])
        assert ip == "203.0.113.195"

    def test_trusted_proxy_uses_rightmost_untrusted_hop(self) -> None:
        scope = {
            "client": ("10.0.0.1", 54321),  # Direct peer is trusted proxy
            "headers": [
                (b"x-forwarded-for", b"203.0.113.50, 10.0.0.2"),
            ],
        }
        # 10.0.0.1 and 10.0.0.2 are trusted proxies
        ip = get_client_ip(scope, trusted_proxies=["10.0.0.1", "10.0.0.2"])
        assert ip == "203.0.113.50"
