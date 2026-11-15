"""URL and argument validation + limit clamping."""
from __future__ import annotations

import re
import urllib.parse

from app.netpolicy import SSRFError, _resolve_and_validate

_URL_CRED_RE = re.compile(r"https?://[^@]+@")


class ValidationError(ValueError):
    def __init__(self, message: str, reason: str = "validation_error") -> None:
        super().__init__(message)
        self.reason = reason


def validate_url(url: str, allow_localhost: bool = False) -> str:
    """
    Validate and normalise a URL.
    - Must be http or https
    - No credentials
    - Host must resolve to a non-forbidden IP
    Returns the normalised URL string.
    """
    url = url.strip()
    if not url:
        raise ValidationError("URL is required", "missing_url")

    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValidationError(
            f"Invalid scheme {parsed.scheme!r}; only http/https allowed", "invalid_scheme"
        )
    if parsed.username or parsed.password:
        raise ValidationError("URL credentials are not allowed", "credentials_in_url")
    if _URL_CRED_RE.match(url):
        raise ValidationError("URL credentials are not allowed", "credentials_in_url")

    host = parsed.hostname
    if not host:
        raise ValidationError("URL has no hostname", "missing_hostname")

    try:
        _resolve_and_validate(host, allow_localhost=allow_localhost)
    except SSRFError as e:
        raise ValidationError(str(e), "ssrf_blocked") from e

    # Reconstruct clean URL (no credentials)
    return url


def clamp_max_pages(value: int, hard_cap: int = 25) -> int:
    return max(1, min(value, hard_cap))


def clamp_max_depth(value: int, hard_cap: int = 3) -> int:
    return max(1, min(value, hard_cap))


def clamp_max_links(value: int, hard_cap: int = 50) -> int:
    return max(1, min(value, hard_cap))
