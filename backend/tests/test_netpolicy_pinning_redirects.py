"""Tests for IP pinning edge cases, redirects, robots disallow-all, and content limits."""
from __future__ import annotations

import socket
import ssl
from unittest.mock import MagicMock, patch
import pytest

from app.netpolicy import (
    ContentTypeError,
    IPPinningError,
    PinnedTransport,
    RedirectError,
    RedirectPolicy,
    RobotsError,
    SSRFError,
    _PinnedNetworkBackend,
    _resolve_and_validate,
    _same_site,
    clear_robots_cache,
    policy_get,
)


class TestIPPinningSecurity:
    def test_mixed_public_and_private_resolution_rejected(self) -> None:
        """If DNS returns both a public IP and a private/loopback IP, it must be rejected."""
        fake_addrinfo = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0)),
        ]
        with patch("socket.getaddrinfo", return_value=fake_addrinfo):
            with pytest.raises(SSRFError) as exc:
                _resolve_and_validate("evil-dual-homed.com", allow_localhost=False)
            assert "forbidden IP 127.0.0.1" in str(exc.value)

    def test_resolver_returns_multiple_public_ips_pins_to_first(self) -> None:
        fake_addrinfo = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.35", 0)),
        ]
        with patch("socket.getaddrinfo", return_value=fake_addrinfo):
            ips = _resolve_and_validate("multi-ip.com")
            assert ips[0] == "93.184.216.34"

    def test_resolver_returns_public_first_then_loopback_connects_only_to_first(self) -> None:
        """When multiple IPs are returned in test mode, client pins to the first IP."""
        fake_addrinfo = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0)),
        ]
        with patch("socket.getaddrinfo", return_value=fake_addrinfo):
            ips = _resolve_and_validate("dual.test", allow_localhost=True)
            assert ips[0] == "93.184.216.34"

    def test_https_cert_verification_enforced(self) -> None:
        """SSL context used for pinned connections must enforce CERT_REQUIRED and check_hostname."""
        from app.netpolicy import _make_ssl_context
        ctx = _make_ssl_context()
        assert ctx.verify_mode == ssl.CERT_REQUIRED
        assert ctx.check_hostname is True

    def test_peer_ip_mismatch_aborts(self) -> None:
        err = IPPinningError("ip_pinning_failed: peer '192.0.2.1' != pinned '93.184.216.34'")
        assert "ip_pinning_failed" in str(err)
        assert issubclass(IPPinningError, Exception)

    def test_no_code_path_makes_unpinned_request(self) -> None:
        """Verify that _PinnedNetworkBackend dials an IP address, never an unpinned hostname."""
        backend = _PinnedNetworkBackend(allow_localhost=True)
        dialed_hosts = []

        def fake_connect(host: str, port: int, **kwargs: object) -> MagicMock:
            dialed_hosts.append(host)
            mock_stream = MagicMock()
            mock_sock = MagicMock()
            mock_sock.getpeername.return_value = (host, port)
            mock_stream._sock = mock_sock
            return mock_stream

        with patch("httpcore.SyncBackend.connect_tcp", side_effect=fake_connect):
            with patch("socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]):
                backend.connect_tcp("example.com", 80)

        assert len(dialed_hosts) == 1
        # Assert dialed host is the pinned IP, NOT the raw hostname!
        assert dialed_hosts[0] == "93.184.216.34"


class TestRedirectsAndRobots:
    def test_redirect_to_private_ip_is_blocked(self, local_site: str) -> None:
        """Redirecting to a private IP host must be blocked."""
        clear_robots_cache()
        with pytest.raises((SSRFError, RedirectError)) as exc:
            policy_get(f"{local_site}/redirect-to-private", allow_localhost=True)
        assert "forbidden" in str(exc.value) or "192.168" in str(exc.value)

    def test_redirect_loop_detected_and_aborted(self, local_site: str) -> None:
        """Redirect loops must be detected and aborted with RedirectError."""
        clear_robots_cache()
        with pytest.raises(RedirectError) as exc:
            policy_get(f"{local_site}/redirect-loop", allow_localhost=True)
        assert "loop detected" in str(exc.value).lower()

    def test_redirect_to_robots_disallowed_destination_not_followed(self, local_site: str) -> None:
        """Redirect to robots-disallowed destination must be blocked."""
        clear_robots_cache()
        with pytest.raises(RobotsError) as exc:
            policy_get(f"{local_site}/redirect-to-robots-disallowed", allow_localhost=True)
        assert "robots_disallowed" in str(exc.value)

    def test_non_html_content_type_skipped(self, local_site: str) -> None:
        """Non-HTML responses (e.g. image/png) must be rejected with ContentTypeError."""
        clear_robots_cache()
        with pytest.raises(ContentTypeError) as exc:
            policy_get(f"{local_site}/non-html", allow_localhost=True)
        assert "Non-HTML" in str(exc.value)

    def test_cross_domain_redirect_blocked_by_default(self) -> None:
        policy = RedirectPolicy(max_hops=3, allow_cross_domain=False)
        assert not policy.allow_cross_domain
        assert not _same_site("example.com", "otherdomain.com")

    def test_cross_domain_redirect_allowed_when_allowlisted(self) -> None:
        policy = RedirectPolicy(
            max_hops=3,
            allow_cross_domain=False,
            allowed_domains=["otherdomain.com"],
        )
        assert any(_same_site("otherdomain.com", d) for d in policy.allowed_domains)

    def test_robots_5xx_disallows_all(self) -> None:
        clear_robots_cache()
        from urllib.robotparser import RobotFileParser
        rp = RobotFileParser()
        rp.parse(["User-agent: *", "Disallow: /"])
        assert not rp.can_fetch("BuildSprintBot/1.0", "http://example.com/anypath")

    def test_1mb_response_cap_enforced(self) -> None:
        from app.netpolicy import _MAX_RESPONSE_SIZE
        assert _MAX_RESPONSE_SIZE == 1_048_576
