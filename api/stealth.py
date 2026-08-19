"""
Stealth layer for API requests — proxy rotation + fingerprint randomization.

Configured via environment variables:
- PROXY_URL: Single rotating proxy URL (http://user:pass@host:port)
- PROXY_LIST: Comma-separated proxy list. Supports formats:
    - http://user:pass@host:port (standard URL)
    - host:port:user:pass (Webshare format)
- STEALTH_ENABLED: true/false (default: true if proxy configured)
- REQUEST_DELAY_MIN: Minimum delay in seconds before request (default: 1.0)
- REQUEST_DELAY_MAX: Maximum delay in seconds before request (default: 3.0)
"""

from __future__ import annotations

import os
import random
import time
from typing import Optional

# ---------------------------------------------------------------------------
# Proxy
# ---------------------------------------------------------------------------

_PROXY_URL = os.getenv("PROXY_URL", "")  # e.g. http://user:pass@gate.smartproxy.com:7777
_PROXY_LIST_RAW = os.getenv("PROXY_LIST", "")  # comma-separated


def _parse_proxy(raw: str) -> str:
    """
    Parse proxy string to http://user:pass@host:port format.
    Supports:
    - http://user:pass@host:port (already valid)
    - host:port:user:pass (Webshare format)
    """
    raw = raw.strip()
    if not raw:
        return ""
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    # Webshare format: host:port:user:pass
    parts = raw.split(":")
    if len(parts) == 4:
        host, port, user, passwd = parts
        return f"http://{user}:{passwd}@{host}:{port}"
    # host:port only (no auth)
    if len(parts) == 2:
        return f"http://{raw}"
    return raw


_PROXY_LIST: list[str] = []
if _PROXY_URL:
    _PROXY_LIST = [_parse_proxy(_PROXY_URL)]
elif _PROXY_LIST_RAW:
    _PROXY_LIST = [
        _parse_proxy(p) for p in _PROXY_LIST_RAW.split(",") if p.strip()
    ]
    _PROXY_LIST = [p for p in _PROXY_LIST if p]  # filter empty

STEALTH_ENABLED = os.getenv("STEALTH_ENABLED", "true" if _PROXY_LIST else "false").lower() == "true"

# Delay jitter (seconds)
REQUEST_DELAY_MIN = float(os.getenv("REQUEST_DELAY_MIN", "1.0"))
REQUEST_DELAY_MAX = float(os.getenv("REQUEST_DELAY_MAX", "3.0"))


def get_proxy() -> Optional[str]:
    """Return a random proxy URL from the pool, or None if no proxies configured."""
    if not _PROXY_LIST:
        return None
    return random.choice(_PROXY_LIST)


# ---------------------------------------------------------------------------
# Header fingerprint randomization
# ---------------------------------------------------------------------------

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
]

_ACCEPT_LANGUAGES = [
    "en-US,en;q=0.9",
    "en-GB,en;q=0.9",
    "en-US,en;q=0.9,id;q=0.8",
    "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
    "en,id;q=0.9",
    "en-US,en;q=0.8",
]

_SEC_CH_UA = [
    '"Chromium";v="125", "Google Chrome";v="125", "Not-A.Brand";v="99"',
    '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    '"Chromium";v="126", "Google Chrome";v="126", "Not-A.Brand";v="99"',
    '"Not/A)Brand";v="8", "Chromium";v="126", "Microsoft Edge";v="126"',
]

_PLATFORMS = [
    '"Windows"',
    '"macOS"',
    '"Linux"',
]


def get_stealth_headers() -> dict:
    """
    Generate randomized browser-like headers.
    These are merged with the actual API headers (API key, Content-Type).
    """
    if not STEALTH_ENABLED:
        return {}

    ua = random.choice(_USER_AGENTS)
    headers = {
        "User-Agent": ua,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": random.choice(_ACCEPT_LANGUAGES),
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "cross-site",
    }

    # Add Sec-CH-UA headers for Chrome-like UAs
    if "Chrome" in ua or "Chromium" in ua:
        headers["Sec-CH-UA"] = random.choice(_SEC_CH_UA)
        headers["Sec-CH-UA-Mobile"] = "?0"
        headers["Sec-CH-UA-Platform"] = random.choice(_PLATFORMS)

    return headers


# ---------------------------------------------------------------------------
# Delay jitter
# ---------------------------------------------------------------------------

def apply_request_delay():
    """Sleep for a random duration to mimic human timing."""
    if not STEALTH_ENABLED:
        return
    delay = random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX)
    time.sleep(delay)
