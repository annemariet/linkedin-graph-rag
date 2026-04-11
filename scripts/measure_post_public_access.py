#!/usr/bin/env python3
"""
Estimate how often LinkedIn post URLs are readable without a logged-in session.

Uses the same signals as enrichment:
- ``linkedin_http_fetch_is_blocked``: signup/login shell (e.g. cold-join) instead of a post.
- ``parse_post_body_from_soup``: extracted body length ≥ 50 counts as "public HTML body".

Examples::

    uv run python scripts/measure_post_public_access.py --limit 50
    uv run python scripts/measure_post_public_access.py ~/.linkedin_api/data/activities.csv --limit 100
    uv run python scripts/measure_post_public_access.py --sleep 1.0
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

# Allow running as ``python scripts/measure_post_public_access.py`` without PYTHONPATH.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from linkedin_api.activity_csv import (
    get_default_csv_path,
    load_records_csv,
)  # noqa: E402
from linkedin_api.utils.post_html import (  # noqa: E402
    linkedin_http_fetch_is_blocked,
    parse_post_body_from_soup,
)
from linkedin_api.utils.urls import is_comment_feed_url  # noqa: E402

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _linkedin_post_urls_from_csv(path: Path) -> list[str]:
    records = load_records_csv(path)
    seen: set[str] = set()
    out: list[str] = []
    for r in records:
        u = (r.post_url or "").strip()
        if not u or u in seen:
            continue
        low = u.lower()
        if "linkedin.com" not in low:
            continue
        if is_comment_feed_url(u):
            continue
        seen.add(u)
        out.append(u)
    return out


def _classify(url: str, timeout: float) -> tuple[str, str]:
    """
    Return (bucket, detail).

    Buckets: error | login_wall | public_body | thin_200
    """
    try:
        resp = requests.get(
            url, timeout=timeout, allow_redirects=True, headers=_HEADERS
        )
    except OSError as e:
        return "error", str(e)[:120]

    if resp.status_code != 200:
        return "error", f"HTTP {resp.status_code}"

    html = resp.text
    final = resp.url or url
    if linkedin_http_fetch_is_blocked(final, html):
        host = urlparse(final).netloc
        return "login_wall", host

    soup = BeautifulSoup(html, "html.parser")
    body = parse_post_body_from_soup(soup)
    if body and len(body) >= 50:
        return "public_body", f"body_chars={len(body)}"

    has_ld = "socialmediaposting" in html.lower()
    if has_ld:
        return "thin_200", "json_ld_present_body_short"
    return "thin_200", f"body_chars={len(body or '')}"


def main() -> int:
    p = argparse.ArgumentParser(
        description="Sample unique post_url values from CSV and classify anonymous fetch outcome.",
    )
    p.add_argument(
        "csv",
        type=Path,
        nargs="?",
        default=None,
        help="activities.csv path (default: master CSV from LINKEDIN_DATA_DIR)",
    )
    p.add_argument(
        "--limit", type=int, default=0, help="Max distinct URLs to probe (0=all)"
    )
    p.add_argument(
        "--timeout", type=float, default=15.0, help="Per-request timeout seconds"
    )
    p.add_argument(
        "--sleep", type=float, default=0.4, help="Delay between requests (seconds)"
    )
    args = p.parse_args()

    csv_path = args.csv or get_default_csv_path()
    if not csv_path.exists():
        print(f"No CSV at {csv_path}", file=sys.stderr)
        print(
            "Pass a path: uv run python scripts/measure_post_public_access.py /path/to/activities.csv"
        )
        return 1

    urls = _linkedin_post_urls_from_csv(csv_path)
    if args.limit and args.limit > 0:
        urls = urls[: args.limit]

    if not urls:
        print(f"No LinkedIn post URLs in {csv_path}")
        return 0

    counts: dict[str, int] = {
        "public_body": 0,
        "login_wall": 0,
        "thin_200": 0,
        "error": 0,
    }
    n = len(urls)
    print(f"CSV: {csv_path}")
    print(
        f"Probing {n} distinct post_url(s) (anonymous GET, timeout={args.timeout}s)\n"
    )

    for i, url in enumerate(urls, 1):
        bucket, detail = _classify(url, args.timeout)
        counts[bucket] += 1
        print(f"[{i}/{n}] {bucket:12} {detail:30} {url[:85]}...")
        if args.sleep > 0 and i < n:
            time.sleep(args.sleep)

    print()
    print("--- Summary ---")
    for k in ("public_body", "login_wall", "thin_200", "error"):
        c = counts[k]
        pct = 100.0 * c / n if n else 0.0
        print(f"  {k:12} {c:4}  ({pct:5.1f}%)")

    print()
    print(
        "Interpretation: ``login_wall`` is our signup/login HTML (no full public post). "
        "``public_body`` matches enrich when we would store HTTP-fetched text. "
        "``thin_200`` is 200 OK but short extract (often SPA shell or non-standard page). "
        "``error`` is network/HTTP failures."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
