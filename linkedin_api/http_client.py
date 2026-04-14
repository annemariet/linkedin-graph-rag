"""Shared HTTP helpers for public LinkedIn page fetches (enrich, backfill, scripts)."""

from __future__ import annotations

import logging
from typing import Final

import requests

from linkedin_api.utils.post_html import linkedin_http_fetch_is_blocked

logger = logging.getLogger(__name__)

LINKEDIN_PUBLIC_FETCH_HEADERS: Final[dict[str, str]] = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def fetch_linkedin_post_html(
    url: str, *, timeout: float = 10.0
) -> tuple[str, str] | None:
    """
    GET a post URL; return ``(html, final_url)`` or ``None`` if unusable.

    Logs the specific failure reason at WARNING level before returning ``None``:
    network errors, non-200 status codes, and login-wall redirects are distinguished.
    """
    try:
        resp = requests.get(
            url,
            timeout=timeout,
            allow_redirects=True,
            headers=LINKEDIN_PUBLIC_FETCH_HEADERS,
        )
    except OSError as e:
        logger.warning("Network error fetching %s: %s", url, e)
        return None
    if resp.status_code != 200:
        logger.warning("HTTP %s fetching %s", resp.status_code, url)
        return None
    final_url = resp.url or url
    if linkedin_http_fetch_is_blocked(final_url, resp.text):
        logger.warning("Login wall fetching %s (landed on %s)", url, final_url)
        return None
    return resp.text, final_url
