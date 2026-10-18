"""Rules for which target URLs shrinkr is willing to redirect to.

These checks look only at the URL text. They don't resolve DNS, so a public name that
points at a private address isn't caught; DNS can change after the check anyway (DNS
rebinding). Whatever *fetches* URLs must protect itself; these rules stop shrinkr from
being an easy tool for reaching private addresses, looping, or hiding destinations.
"""

import ipaddress
import os

from pydantic import HttpUrl

# Names that only mean something inside a machine or private network.
LOCAL_SUFFIXES = (".localhost", ".local", ".internal", ".lan", ".home.arpa")

# Other URL shorteners: chaining them hides the real destination (a phishing favourite).
DEFAULT_BLOCKED_DOMAINS = {
    "bit.ly", "cutt.ly", "goo.gl", "is.gd", "ow.ly", "rebrand.ly", "t.co", "tinyurl.com",
}


def _domains_from_env() -> set[str]:
    # BLOCKED_DOMAINS="evil.example,spam.example" adds to the defaults.
    raw = os.getenv("BLOCKED_DOMAINS", "")
    return {d.strip().lower().rstrip(".") for d in raw.split(",") if d.strip()}


BLOCKED_DOMAINS = DEFAULT_BLOCKED_DOMAINS | _domains_from_env()

NOT_PUBLIC = "Links to private or local network addresses are not allowed"


def unsafe_reason(url: HttpUrl, own_host: str | None) -> str | None:
    """Why this URL must not be shortened, or None if it's acceptable."""
    if url.username or url.password:
        # e.g. https://paypal.com@evil.com/ really goes to evil.com
        return "URLs containing a username or password are not allowed"

    # Normalise: "[::1]" → "::1"; "localhost." (trailing dot) means the same as "localhost".
    host = (url.host or "").strip("[]").rstrip(".").lower()

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None:
        # "::ffff:7f00:1" is IPv4 127.0.0.1 written as IPv6. Python 3.13+ already accounts
        # for this in is_global; unwrapping explicitly keeps the rule obvious and version-proof.
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        # is_global is False for loopback, private, link-local (169.254.x: cloud metadata),
        # carrier-grade NAT, reserved and unspecified (0.0.0.0) ranges.
        return None if ip.is_global else NOT_PUBLIC

    if own_host and host == own_host.lower():
        return "Links to shrinkr itself are not allowed (they could create redirect loops)"
    if host == "localhost" or host.endswith(LOCAL_SUFFIXES) or "." not in host:
        return NOT_PUBLIC
    if any(host == domain or host.endswith("." + domain) for domain in BLOCKED_DOMAINS):
        return "Links to this domain are not allowed"
    return None
