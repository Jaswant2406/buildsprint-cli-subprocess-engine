"""
Shared network policy: SSRF prevention, IP pinning, redirect policy, robots.txt.
Used by BOTH cli/site_crawler.py and cli/link_checker.py.

IP pinning: custom httpcore NetworkBackend that resolves → validates → pins to IP,
while passing server_hostname=original_host for TLS SNI + certificate verification.
"""
from __future__ import annotations

import ipaddress
import socket
import ssl
import urllib.parse
import urllib.robotparser
from dataclasses import dataclass, field
from typing import Iterable

import httpcore
import httpx

# ---------------------------------------------------------------------------
# SSL helper
# ---------------------------------------------------------------------------


def _make_ssl_context() -> ssl.SSLContext:
    """Create an SSL context with certifi CA bundle if available."""
    try:
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        ctx = ssl.create_default_context()
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED
    return ctx


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

METADATA_IPS: set[str] = {
    "169.254.169.254",  # AWS / Azure / GCP metadata
    "fd00:ec2::254",    # IPv6 metadata
    "100.100.100.200",  # Alibaba metadata
}

SAFE_SCHEMES = {"http", "https"}
_MAX_RESPONSE_SIZE = 1_048_576  # 1 MB


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class NetworkPolicyError(Exception):
    """Base class for all network policy violations."""
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class SSRFError(NetworkPolicyError):
    pass


class IPPinningError(NetworkPolicyError):
    pass


class RedirectError(NetworkPolicyError):
    pass


class RobotsError(NetworkPolicyError):
    pass


class ContentTypeError(NetworkPolicyError):
    pass


# ---------------------------------------------------------------------------
# IP validation helpers
# ---------------------------------------------------------------------------


def _parse_alternative_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """Try to parse decimal/octal/hex encoded IPs that bypass naive checks."""
    try:
        val = int(host, 0)
        return ipaddress.IPv4Address(val)
    except (ValueError, ipaddress.AddressValueError):
        pass
    try:
        parts = host.split(".")
        if 2 <= len(parts) <= 4:
            dec_parts = []
            for p in parts:
                if p.startswith("0x") or p.startswith("0X"):
                    dec_parts.append(int(p, 16))
                elif p.startswith("0") and len(p) > 1:
                    dec_parts.append(int(p, 8))
                else:
                    dec_parts.append(int(p, 10))
            return ipaddress.IPv4Address(".".join(str(x) for x in dec_parts))
    except (ValueError, ipaddress.AddressValueError):
        pass
    return None


def _is_forbidden_ip(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> tuple[bool, str]:
    """Return (True, reason) if the address is forbidden."""
    checks: list[tuple[bool, str]] = [
        (addr.is_loopback, "loopback"),
        (addr.is_link_local, "link_local"),
        (addr.is_multicast, "multicast"),
        (addr.is_reserved, "reserved"),
        (addr.is_unspecified, "unspecified"),
        (addr.is_private, "private"),
    ]
    for predicate, reason in checks:
        if predicate:
            return True, reason

    for meta in METADATA_IPS:
        try:
            if addr == ipaddress.ip_address(meta):
                return True, "metadata_service"
        except ValueError:
            pass

    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        return _is_forbidden_ip(addr.ipv4_mapped)

    return False, ""


def _resolve_and_validate(
    host: str,
    allow_localhost: bool = False,
) -> list[str]:
    """
    Resolve host to all IPs; raise SSRFError if any is forbidden.
    Returns list of validated IP strings.
    """
    alt = _parse_alternative_ip(host)
    if alt is not None:
        forbidden, reason = _is_forbidden_ip(alt)
        if forbidden and not (allow_localhost and alt.is_loopback):
            raise SSRFError(f"Encoded IP {host!r} resolves to forbidden address: {reason}")
        return [str(alt)]

    try:
        infos = socket.getaddrinfo(host, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise SSRFError(f"DNS resolution failed for {host!r}: {e}") from e

    resolved: list[str] = []
    for info in infos:
        raw_ip = str(info[4][0])
        try:
            addr = ipaddress.ip_address(raw_ip)
        except ValueError:
            continue
        forbidden, reason = _is_forbidden_ip(addr)
        if forbidden:
            if allow_localhost and addr.is_loopback:
                resolved.append(raw_ip)
                continue
            raise SSRFError(
                f"Host {host!r} resolves to forbidden IP {raw_ip} ({reason})"
            )
        resolved.append(raw_ip)

    if not resolved:
        raise SSRFError(f"No valid IPs resolved for {host!r}")
    return list(dict.fromkeys(resolved))


# ---------------------------------------------------------------------------
# Pinned network backend for httpcore
# ---------------------------------------------------------------------------


class _PinnedNetworkBackend(httpcore.SyncBackend):
    """
    Override connect_tcp to:
    1. Resolve host -> validate all IPs -> pin to first
    2. Connect to pinned IP (not hostname) preventing DNS rebind / TOCTOU
    3. Verify peer address equals pinned IP
    4. Pass server_hostname=original_host so TLS SNI and cert verification work
    """

    def __init__(self, allow_localhost: bool = False) -> None:
        super().__init__()
        self._allow_localhost = allow_localhost
        self._pinned_map: dict[str, str] = {}  # host -> pinned_ip

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.NetworkStream:
        # Validate scheme (host-only here)
        alt = _parse_alternative_ip(host)
        if alt is not None:
            forbidden, reason = _is_forbidden_ip(alt)
            if forbidden and not (self._allow_localhost and alt.is_loopback):
                raise SSRFError(f"Encoded IP {host!r} is forbidden: {reason}")
            pinned_ip = str(alt)
        else:
            # Full DNS resolve + validate
            ips = _resolve_and_validate(host, allow_localhost=self._allow_localhost)
            pinned_ip = ips[0]

        # Connect to pinned IP; pass server_hostname for SNI
        # httpcore's connect_tcp already handles TLS wrapping via ssl_context
        # We dial pinned_ip but tell httpcore the hostname is `host` for SNI
        stream = super().connect_tcp(
            host=pinned_ip,  # Connect to IP, not hostname
            port=port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )

        # Verify peer IP post-connect
        raw_sock = getattr(stream, "_sock", None)
        if raw_sock is None:
            stream.close()
            raise IPPinningError("ip_pinning_failed: unable to inspect socket")

        try:
            peer = raw_sock.getpeername()
            peer_ip = peer[0] if isinstance(peer, tuple) else str(peer)
            peer_norm = peer_ip.split("%")[0]
            pinned_norm = pinned_ip.split("%")[0]
            if peer_norm != pinned_norm:
                stream.close()
                raise IPPinningError(
                    f"ip_pinning_failed: peer {peer_ip!r} != pinned {pinned_ip!r}"
                )
        except OSError as e:
            stream.close()
            raise IPPinningError(f"ip_pinning_failed: getpeername failed: {e}") from e

        # Store original hostname so TLS wrapper uses correct SNI
        self._pinned_map[pinned_ip] = host
        return stream


class PinnedTransport(httpx.BaseTransport):
    """
    httpx transport using the pinned network backend.
    Uses httpcore's ConnectionPool with our custom backend that pins IPs.
    """

    def __init__(
        self,
        allow_localhost: bool = False,
        connect_timeout: float = 10.0,
        read_timeout: float = 20.0,
    ) -> None:
        self._allow_localhost = allow_localhost
        ssl_context = _make_ssl_context()
        backend = _PinnedNetworkBackend(allow_localhost=allow_localhost)
        self._pool = httpcore.ConnectionPool(
            ssl_context=ssl_context,
            network_backend=backend,
            max_connections=10,
        )

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host
        scheme = request.url.scheme

        # Validate scheme
        if scheme not in SAFE_SCHEMES:
            raise SSRFError(f"Forbidden scheme: {scheme!r}")

        # Credentials in URL
        if request.url.username or request.url.password:
            raise SSRFError("URL credentials are forbidden")

        # Pre-validate host (raises SSRFError before any connection attempt)
        alt = _parse_alternative_ip(host)
        if alt is not None:
            forbidden, reason = _is_forbidden_ip(alt)
            if forbidden and not (self._allow_localhost and alt.is_loopback):
                raise SSRFError(f"Encoded IP {host!r} is forbidden: {reason}")
        else:
            _resolve_and_validate(host, allow_localhost=self._allow_localhost)

        # Build httpcore request
        core_request = httpcore.Request(
            method=request.method,
            url=str(request.url),
            headers=list(request.headers.raw),
            content=request.stream,
            extensions={"server_hostname": host.encode()},
        )
        with self._pool as pool:
            core_response = pool.handle_request(core_request)
            # Collect the full response body
            content = b"".join(iter(core_response.stream))  # type: ignore[arg-type]
            if len(content) > _MAX_RESPONSE_SIZE:
                content = content[:_MAX_RESPONSE_SIZE]

        return httpx.Response(
            status_code=core_response.status,
            headers=[
                (k.decode() if isinstance(k, bytes) else k,
                 v.decode() if isinstance(v, bytes) else v)
                for k, v in core_response.headers
            ],
            content=content,
            request=request,
        )

    def close(self) -> None:
        self._pool.close()


# ---------------------------------------------------------------------------
# robots.txt cache
# ---------------------------------------------------------------------------

_robots_cache: dict[str, urllib.robotparser.RobotFileParser | None] = {}


def _get_robots(
    scheme: str,
    host: str,
    allow_localhost: bool = False,
    user_agent: str = "BuildSprintBot/1.0",
) -> urllib.robotparser.RobotFileParser | None:
    key = f"{scheme}://{host}"
    if key in _robots_cache:
        return _robots_cache[key]

    rp = urllib.robotparser.RobotFileParser()
    robots_url = f"{scheme}://{host}/robots.txt"
    try:
        with _build_client(allow_localhost=allow_localhost, timeout=10.0, user_agent=user_agent) as client:
            resp = client.request("GET", robots_url)
            if resp.status_code == 404:
                _robots_cache[key] = None
                return None
            if resp.status_code >= 500:
                rp.parse(["User-agent: *", "Disallow: /"])
                _robots_cache[key] = rp
                return rp
            rp.set_url(robots_url)
            rp.parse(resp.text.splitlines())
    except (SSRFError, IPPinningError):
        _robots_cache[key] = None
        return None
    except Exception:
        _robots_cache[key] = None
        return None

    _robots_cache[key] = rp
    return rp


def _is_robots_allowed(
    url: str,
    allow_localhost: bool = False,
    user_agent: str = "BuildSprintBot/1.0",
) -> bool:
    parsed = urllib.parse.urlparse(url)
    rp = _get_robots(
        parsed.scheme,
        parsed.netloc,
        allow_localhost=allow_localhost,
        user_agent=user_agent,
    )
    if rp is None:
        return True
    return rp.can_fetch(user_agent, url)


def _same_site(host1: str, host2: str) -> bool:
    h1 = host1.lower().lstrip("www.")
    h2 = host2.lower().lstrip("www.")
    return h1 == h2


# ---------------------------------------------------------------------------
# Request helpers
# ---------------------------------------------------------------------------


@dataclass
class RedirectPolicy:
    max_hops: int = 3
    allow_cross_domain: bool = False
    allowed_domains: list[str] = field(default_factory=list)


def _build_client(
    allow_localhost: bool = False,
    timeout: float = 15.0,
    user_agent: str = "BuildSprintBot/1.0",
) -> httpx.Client:
    transport = PinnedTransport(
        allow_localhost=allow_localhost,
        connect_timeout=min(timeout, 10.0),
        read_timeout=timeout,
    )
    return httpx.Client(
        transport=transport,
        follow_redirects=False,
        timeout=timeout,
        headers={"User-Agent": user_agent},
    )


def _raw_get(
    client: httpx.Client,
    url: str,
    allow_localhost: bool = False,
    check_robots: bool = True,
    user_agent: str = "BuildSprintBot/1.0",
) -> httpx.Response | None:
    """Single-hop GET; does NOT follow redirects."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in SAFE_SCHEMES:
        raise SSRFError(f"Forbidden scheme: {parsed.scheme!r}")
    if parsed.username or parsed.password:
        raise SSRFError("URL credentials are forbidden")
    if check_robots and not _is_robots_allowed(url, allow_localhost=allow_localhost, user_agent=user_agent):
        raise RobotsError(f"robots.txt disallows {url!r}")

    resp = client.request("GET", url)
    ct = resp.headers.get("content-type", "")
    if resp.status_code < 300:
        # Allow text/* and application/json; skip binary content
        if ct and not any(t in ct for t in (
            "text/html", "application/xhtml+xml", "text/plain",
            "application/json", "text/",
        )):
            if not ct.startswith("text/"):
                return None
        if len(resp.content) > _MAX_RESPONSE_SIZE:
            raise ContentTypeError("Response exceeds 1MB cap")
    return resp


def policy_get(
    url: str,
    allow_localhost: bool = False,
    redirect_policy: RedirectPolicy | None = None,
    user_agent: str = "BuildSprintBot/1.0",
    check_robots: bool = True,
) -> httpx.Response:
    """
    Full policy-compliant GET: SSRF check, IP pinning, manual redirects,
    robots.txt check at each hop.
    """
    if redirect_policy is None:
        redirect_policy = RedirectPolicy()

    visited: set[str] = set()
    current_url = url
    origin_host = urllib.parse.urlparse(url).netloc

    with _build_client(allow_localhost=allow_localhost, user_agent=user_agent) as client:
        for hop in range(redirect_policy.max_hops + 1):
            if current_url in visited:
                raise RedirectError(f"Redirect loop detected at {current_url!r}")
            visited.add(current_url)

            parsed = urllib.parse.urlparse(current_url)
            current_host = parsed.netloc

            # Cross-domain check
            if not _same_site(origin_host, current_host):
                if not redirect_policy.allow_cross_domain:
                    allowed = any(
                        _same_site(current_host, d) for d in redirect_policy.allowed_domains
                    )
                    if not allowed:
                        raise RedirectError(
                            f"cross_domain_redirect_blocked: {current_url!r}"
                        )

            resp = _raw_get(
                client,
                current_url,
                allow_localhost=allow_localhost,
                check_robots=check_robots,
                user_agent=user_agent,
            )
            if resp is None:
                raise ContentTypeError(f"Non-HTML content at {current_url!r}")

            if resp.status_code not in (301, 302, 303, 307, 308):
                return resp

            if hop >= redirect_policy.max_hops:
                raise RedirectError("redirect limit exceeded")

            location = resp.headers.get("location", "")
            if not location:
                raise RedirectError("Redirect with no Location header")

            next_url = urllib.parse.urljoin(current_url, location)
            next_parsed = urllib.parse.urlparse(next_url)
            if next_parsed.scheme not in SAFE_SCHEMES:
                raise RedirectError(f"Redirect to forbidden scheme: {next_parsed.scheme!r}")

            _resolve_and_validate(next_parsed.hostname or "", allow_localhost=allow_localhost)

            if check_robots and not _is_robots_allowed(
                next_url, allow_localhost=allow_localhost, user_agent=user_agent
            ):
                raise RobotsError(f"robots_disallowed_redirect: {next_url!r}")

            current_url = next_url

    raise RedirectError("redirect limit exceeded")


def policy_head(
    url: str,
    allow_localhost: bool = False,
    user_agent: str = "BuildSprintBot/1.0",
) -> httpx.Response:
    """HEAD request with SSRF + IP pinning validation."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in SAFE_SCHEMES:
        raise SSRFError(f"Forbidden scheme: {parsed.scheme!r}")

    with _build_client(allow_localhost=allow_localhost, user_agent=user_agent) as client:
        resp = client.request("HEAD", url)
    return resp


def clear_robots_cache() -> None:
    """Clear the robots.txt cache."""
    _robots_cache.clear()
