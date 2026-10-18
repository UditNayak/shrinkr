import ipaddress
import os

from pydantic import HttpUrl

LOCAL_SUFFIXES = (".localhost", ".local", ".internal", ".lan", ".home.arpa")
DEFAULT_BLOCKED_DOMAINS = {
    "bit.ly", "cutt.ly", "goo.gl", "is.gd", "ow.ly", "rebrand.ly", "t.co", "tinyurl.com",
}


def _domains_from_env() -> set[str]:
    raw = os.getenv("BLOCKED_DOMAINS", "")
    return {d.strip().lower().rstrip(".") for d in raw.split(",") if d.strip()}


BLOCKED_DOMAINS = DEFAULT_BLOCKED_DOMAINS | _domains_from_env()

NOT_PUBLIC = "Links to private or local network addresses are not allowed"


def unsafe_reason(url: HttpUrl, own_host: str | None) -> str | None:
    """Return why the URL can't be shortened, or None if it's fine. Checks the text only, no DNS."""
    # https://paypal.com@evil.com actually goes to evil.com
    if url.username or url.password:
        return "URLs containing a username or password are not allowed"

    # "[::1]" -> "::1", and "localhost." is the same host as "localhost"
    host = (url.host or "").strip("[]").rstrip(".").lower()

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None:
        # ::ffff:127.0.0.1 is IPv4 written as IPv6
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        # is_global is false for private, loopback, link-local (cloud metadata) and reserved ranges
        return None if ip.is_global else NOT_PUBLIC

    if own_host and host == own_host.lower():
        return "Links to shrinkr itself are not allowed (they could create redirect loops)"
    if host == "localhost" or host.endswith(LOCAL_SUFFIXES) or "." not in host:
        return NOT_PUBLIC
    if any(host == domain or host.endswith("." + domain) for domain in BLOCKED_DOMAINS):
        return "Links to this domain are not allowed"
    return None
