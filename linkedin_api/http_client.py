"""Shared HTTP helpers for public LinkedIn page fetches (enrich, backfill, scripts)."""

from __future__ import annotations

from typing import Final

import requests

from linkedin_api.utils.post_html import linkedin_http_fetch_is_blocked

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

    Same behavior as the previous inline logic in ``enrich_activities`` /
    ``backfill_content_store``: non-200, network error, or login-wall HTML → ``None``.
    """
    try:
        resp = requests.get(
            url,
            timeout=timeout,
            allow_redirects=True,
            headers=LINKEDIN_PUBLIC_FETCH_HEADERS,
        )
    except OSError:
        return None
    if resp.status_code != 200:
        return None
    if linkedin_http_fetch_is_blocked(resp.url, resp.text):
        return None
    return resp.text, resp.url or url
