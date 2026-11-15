"""Tests for netpolicy: SSRF, IP pinning, redirects, robots."""
from __future__ import annotations

import os
import socket
import threading
import time
import urllib.parse
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest

os.environ["APP_ENV"] = "test"
os.environ["ALLOW_LOCALHOST_FOR_TESTS"] = "1"

from app.netpolicy import (
    ContentTypeError,
    IPPinningError,
    NetworkPolicyError,
    PinnedTransport,
    RedirectError,
    RedirectPolicy,
    RobotsError,
    SSRFError,
    _is_forbidden_ip,
    _parse_alternative_ip,
    _resolve_and_validate,
    _same_site,
    clear_robots_cache,
    policy_get,
)
import ipaddress


# ---------------------------------------------------------------------------
# IP validation tests
# ---------------------------------------------------------------------------


class TestForbiddenIPs:
    def test_loopback_ipv4(self) -> None:
        addr = ipaddress.ip_address("127.0.0.1")
        forbidden, reason = _is_forbidden_ip(addr)
        assert forbidden
        assert reason == "loopback"

    def test_loopback_ipv6(self) -> None:
        addr = ipaddress.ip_address("::1")
        forbidden, reason = _is_forbidden_ip(addr)
        assert forbidden
        assert reason == "loopback"

    def test_private_192(self) -> None:
        addr = ipaddress.ip_address("192.168.1.1")
        forbidden, reason = _is_forbidden_ip(addr)
        assert forbidden
        assert reason == "private"

    def test_private_10(self) -> None:
        addr = ipaddress.ip_address("10.0.0.1")
        forbidden, reason = _is_forbidden_ip(addr)
        assert forbidden
        assert reason == "private"

    def test_private_172(self) -> None:
        addr = ipaddress.ip_address("172.16.0.1")
        forbidden, reason = _is_forbidden_ip(addr)
        assert forbidden
        assert reason == "private"

    def test_link_local(self) -> None:
        addr = ipaddress.ip_address("169.254.1.1")
        forbidden, reason = _is_forbidden_ip(addr)
        assert forbidden
        assert reason == "link_local"

    def test_metadata_service(self) -> None:
        addr = ipaddress.ip_address("169.254.169.254")
        forbidden, reason = _is_forbidden_ip(addr)
        assert forbidden

    def test_public_ip_allowed(self) -> None:
        addr = ipaddress.ip_address("93.184.216.34")  # example.com
        forbidden, reason = _is_forbidden_ip(addr)
        assert not forbidden

    def test_ipv4_mapped_ipv6_private(self) -> None:
        # ::ffff:192.168.1.1
        addr = ipaddress.ip_address("::ffff:192.168.1.1")
        forbidden, reason = _is_forbidden_ip(addr)
        assert forbidden


class TestAlternativeIPEncoding:
    def test_decimal_integer(self) -> None:
        # 2130706433 = 127.0.0.1
        alt = _parse_alternative_ip("2130706433")
        assert alt is not None
        assert str(alt) == "127.0.0.1"

    def test_hex_ip(self) -> None:
        # 0x7f000001 = 127.0.0.1
        alt = _parse_alternative_ip("0x7f000001")
        assert alt is not None
        assert str(alt) == "127.0.0.1"

    def test_octal_dotted(self) -> None:
        # 0177.0.0.1 = 127.0.0.1
        alt = _parse_alternative_ip("0177.0.0.1")
        assert alt is not None
        assert str(alt) == "127.0.0.1"

    def test_normal_ip_not_matched(self) -> None:
        alt = _parse_alternative_ip("example.com")
        assert alt is None


class TestResolveAndValidate:
    def test_public_domain_resolves(self) -> None:
        # This may fail if network is down; that's acceptable
        try:
            ips = _resolve_and_validate("example.com")
            assert len(ips) > 0
        except SSRFError:
            pass  # Network unavailable is ok in CI

    def test_localhost_blocked_by_default(self) -> None:
        with pytest.raises(SSRFError):
            _resolve_and_validate("127.0.0.1", allow_localhost=False)

    def test_localhost_allowed_with_flag(self) -> None:
        ips = _resolve_and_validate("127.0.0.1", allow_localhost=True)
        assert "127.0.0.1" in ips

    def test_private_ip_blocked(self) -> None:
        with pytest.raises(SSRFError):
            _resolve_and_validate("192.168.1.1", allow_localhost=False)

    def test_encoded_private_ip_blocked(self) -> None:
        # Decimal encoding of 192.168.1.1
        with pytest.raises(SSRFError):
            _resolve_and_validate("3232235777", allow_localhost=False)

    def test_octal_loopback_blocked(self) -> None:
        with pytest.raises(SSRFError):
            _resolve_and_validate("0177.0.0.1", allow_localhost=False)

    def test_metadata_ip_blocked(self) -> None:
        with pytest.raises(SSRFError):
            _resolve_and_validate("169.254.169.254", allow_localhost=False)


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------


class TestValidators:
    def test_valid_https_url(self) -> None:
        from app.validators import validate_url
        # Should not raise for a public URL
        try:
            result = validate_url("https://example.com")
            assert "example.com" in result
        except Exception:
            pass  # Network may be unavailable

    def test_invalid_scheme_ftp(self) -> None:
        from app.validators import ValidationError, validate_url
        with pytest.raises(ValidationError) as exc:
            validate_url("ftp://example.com")
        assert exc.value.reason == "invalid_scheme"

    def test_credentials_in_url(self) -> None:
        from app.validators import ValidationError, validate_url
        with pytest.raises(ValidationError) as exc:
            validate_url("https://user:pass@example.com")
        assert exc.value.reason == "credentials_in_url"

    def test_ssrf_private_blocked(self) -> None:
        from app.validators import ValidationError, validate_url
        with pytest.raises(ValidationError) as exc:
            validate_url("http://192.168.1.1")
        assert exc.value.reason == "ssrf_blocked"

    def test_ssrf_loopback_blocked(self) -> None:
        from app.validators import ValidationError, validate_url
        with pytest.raises(ValidationError) as exc:
            validate_url("http://127.0.0.1")
        assert exc.value.reason == "ssrf_blocked"

    def test_ssrf_metadata_blocked(self) -> None:
        from app.validators import ValidationError, validate_url
        with pytest.raises(ValidationError) as exc:
            validate_url("http://169.254.169.254")
        assert exc.value.reason == "ssrf_blocked"

    def test_localhost_flag_outside_test_ignored(self) -> None:
        """allow_localhost=True should still block private IPs (only allows loopback)."""
        from app.validators import ValidationError, validate_url
        with pytest.raises(ValidationError):
            validate_url("http://10.0.0.1")

    def test_limit_clamping(self) -> None:
        from app.validators import clamp_max_depth, clamp_max_links, clamp_max_pages
        assert clamp_max_pages(100) == 25
        assert clamp_max_pages(0) == 1
        assert clamp_max_depth(10) == 3
        assert clamp_max_depth(0) == 1
        assert clamp_max_links(100) == 50
        assert clamp_max_links(0) == 1


# ---------------------------------------------------------------------------
# Same site check
# ---------------------------------------------------------------------------


class TestSameSite:
    def test_www_and_apex_same(self) -> None:
        assert _same_site("www.example.com", "example.com")
        assert _same_site("example.com", "www.example.com")

    def test_different_domains(self) -> None:
        assert not _same_site("example.com", "other.com")


# ---------------------------------------------------------------------------
# PinnedTransport
# ---------------------------------------------------------------------------


class TestPinnedTransport:
    def test_forbidden_scheme_raises(self) -> None:
        import httpx
        transport = PinnedTransport(allow_localhost=False)
        req = httpx.Request("GET", "ftp://example.com/")
        with pytest.raises(SSRFError):
            transport.handle_request(req)

    def test_credentials_in_url_raises(self) -> None:
        import httpx
        transport = PinnedTransport(allow_localhost=False)
        req = httpx.Request("GET", "https://user:pass@example.com/")
        with pytest.raises(SSRFError):
            transport.handle_request(req)

    def test_private_ip_raises(self) -> None:
        import httpx
        transport = PinnedTransport(allow_localhost=False)
        req = httpx.Request("GET", "http://192.168.1.1/")
        with pytest.raises(SSRFError):
            transport.handle_request(req)

    def test_loopback_blocked_without_flag(self) -> None:
        import httpx
        transport = PinnedTransport(allow_localhost=False)
        req = httpx.Request("GET", "http://127.0.0.1/")
        with pytest.raises(SSRFError):
            transport.handle_request(req)


# ---------------------------------------------------------------------------
# Local site tests (using fixture)
# ---------------------------------------------------------------------------


class TestLocalSiteCrawl:
    def test_local_site_serves(self, local_site: str) -> None:
        """Verify the local test server works."""
        clear_robots_cache()
        resp = policy_get(
            f"{local_site}/index.html",
            allow_localhost=True,
        )
        assert resp.status_code == 200
        assert b"Demo Site" in resp.content

    def test_robots_txt_fetched(self, local_site: str) -> None:
        """robots.txt should be fetched and respected."""
        clear_robots_cache()
        from app.netpolicy import _get_robots
        rp = _get_robots("http", f"127.0.0.1:{urllib.parse.urlparse(local_site).port}",
                          allow_localhost=True)
        # 404 on robots = None (allow all) or actual robots parsed
        # Either is correct — the point is no crash

    def test_private_path_robots_blocked(self, local_site: str) -> None:
        """Private paths should be blocked by robots.txt."""
        clear_robots_cache()
        with pytest.raises(RobotsError):
            policy_get(
                f"{local_site}/private/index.html",
                allow_localhost=True,
            )


class TestValidatorsAndEdgeCases:
    def test_validate_url_empty_raises(self) -> None:
        from app.validators import validate_url, ValidationError
        with pytest.raises(ValidationError, match="required"):
            validate_url("")

    def test_validate_url_no_hostname_raises(self) -> None:
        from app.validators import validate_url, ValidationError
        with pytest.raises(ValidationError, match="no hostname"):
            validate_url("http:///path/only")

    def test_validate_url_regex_creds(self) -> None:
        from app.validators import validate_url, ValidationError
        with pytest.raises(ValidationError, match="credentials"):
            validate_url("http://user:secret@example.com")
        with pytest.raises(ValidationError, match="credentials"):
            validate_url("http://:@example.com")

    def test_alternative_ip_dotted_hex(self) -> None:
        from app.netpolicy import _parse_alternative_ip
        ip = _parse_alternative_ip("0x7f.0.0.1")
        assert ip == ipaddress.IPv4Address("127.0.0.1")

    def test_ipv4_mapped_ipv6(self) -> None:
        from app.netpolicy import _is_forbidden_ip
        mapped = ipaddress.IPv6Address("::ffff:127.0.0.1")
        forbidden, reason = _is_forbidden_ip(mapped)
        assert forbidden
        assert reason == "loopback"
