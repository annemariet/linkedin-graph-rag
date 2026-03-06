#!/usr/bin/env python3
"""
Enrich activities with post content and linked URLs.

Reads activities JSON (from summarize_activity). For each activity with post_url
that has not been processed yet:

1. Persists URLs already extracted from API text (present in the activities record).
2. Fetches the post page via HTTP to obtain content (when not already stored) and
   additional URLs from the rendered page. Both sources are merged.

Content is only saved to the store when it was not already available.
URLs from API text are saved even when the HTTP fetch fails (e.g. login required).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from linkedin_api.content_store import (
    has_metadata,
    load_content,
    save_content,
    save_metadata,
)
from linkedin_api.extract_resources import extract_urls_from_text

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs"

_CONTENT_SELECTORS = [
    "article[data-id]",
    ".feed-shared-update-v2__description",
    ".feed-shared-text",
    '[data-test-id="main-feed-activity-card"]',
]


def _parse_content_from_html(html: str) -> str:
    """Extract post body text from LinkedIn page HTML."""
    soup = BeautifulSoup(html, "html.parser")
    content_text = []
    for selector in _CONTENT_SELECTORS:
        for elem in soup.select(selector):
            text = elem.get_text(strip=True)
            if text and len(text) > 20:
                content_text.append(text)
    if content_text:
        return "\n".join(content_text)
    og = soup.find("meta", property="og:description")
    if og and og.get("content"):
        content_text.append(str(og["content"]))
    title = soup.find("title")
    if title:
        t = title.get_text(strip=True)
        if " | " in t:
            content_text.append(t.split(" | ")[0])
    return "\n".join(content_text) if content_text else ""


def _is_comment_feed_url(url: str) -> bool:
    """True if URL targets a comment (not a post); skip for content extraction."""
    return bool(url and "urn:li:comment:" in url)


def _fetch_with_requests(url: str) -> tuple[str, list[str]] | None:
    """
    Try simple HTTP request. Returns (content, urls) if successful, None on
    non-200, empty content, or error. LinkedIn returns proper status codes
    (e.g. 403) when login is required.
    """
    try:
        resp = requests.get(url, timeout=10, allow_redirects=True)
        if resp.status_code != 200:
            return None
        content = _parse_content_from_html(resp.text)
        if not content or len(content) < 50:
            return None
        return content, extract_urls_from_text(content)
    except Exception:
        return None


def _run_enrichment(to_enrich: list[dict]):
    """
    Generator: for each record, persist URLs from API text and attempt HTTP fetch
    for post content and additional URLs. Yields (done, total) after each item.
    Returns enriched_count via StopIteration.
    """
    total = len(to_enrich)
    enriched_count = 0
    needs_browser: list[dict] = []

    for i, rec in enumerate(to_enrich):
        urn = rec.get("post_urn", "")
        url = rec.get("post_url", "")
        if urn and url:
            # URLs already extracted from API text by summarize_activity
            urls_from_api = rec.get("urls") or []

            # 1) Content already in store (e.g. from a previous HTTP fetch)
            stored = load_content(urn)
            if stored and len(stored) >= 50:
                if not rec.get("content"):
                    rec["content"] = stored
                rec["urls"] = list(dict.fromkeys(urls_from_api))
                save_metadata(urn, urls=rec["urls"], post_url=url)
                enriched_count += 1
            else:
                # 2) Try HTTP fetch for content and additional URLs
                result = _fetch_with_requests(url)
                if result:
                    fetched_content, fetched_urls = result
                    all_urls = list(dict.fromkeys(urls_from_api + fetched_urls))
                    rec["urls"] = all_urls
                    if not rec.get("content"):
                        rec["content"] = fetched_content
                        save_content(urn, fetched_content)
                    save_metadata(urn, urls=all_urls, post_url=url)
                    enriched_count += 1
                elif urls_from_api:
                    # HTTP failed (e.g. login required) but API text had URLs
                    rec["urls"] = urls_from_api
                    save_metadata(urn, urls=urls_from_api, post_url=url)
                    enriched_count += 1
                else:
                    needs_browser.append(rec)
        yield i + 1, total

    for rec in needs_browser:
        rec["_enrich_error"] = "Browser required; not implemented"
    return enriched_count


def enrich_activities(
    activities: list[dict],
    *,
    limit: int | None = None,
) -> tuple[list[dict], int]:
    """
    Enrich activities that have post_url and have not been processed yet.
    Returns (enriched_activities, count_enriched).
    """
    to_enrich = [
        a
        for a in activities
        if a.get("post_url")
        and not _is_comment_feed_url(a.get("post_url", ""))
        and not has_metadata(a.get("post_urn", ""))
    ]
    if limit:
        to_enrich = to_enrich[:limit]
    if not to_enrich:
        return activities, 0

    gen = _run_enrichment(to_enrich)
    try:
        while True:
            next(gen)
    except StopIteration as e:
        return activities, e.value


def enrich_activities_streaming(
    activities: list[dict],
    *,
    limit: int | None = None,
):
    """
    Generator variant of enrich_activities.
    Yields (done, total) after each activity processed.
    Returns (activities, count_enriched) via StopIteration.value.
    """
    to_enrich = [
        a
        for a in activities
        if a.get("post_url")
        and not _is_comment_feed_url(a.get("post_url", ""))
        and not has_metadata(a.get("post_urn", ""))
    ]
    if limit:
        to_enrich = to_enrich[:limit]
    if not to_enrich:
        return activities, 0

    gen = _run_enrichment(to_enrich)
    try:
        while True:
            yield next(gen)
    except StopIteration as e:
        return activities, e.value


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Enrich activities with post content (HTTP and store only).",
    )
    parser.add_argument(
        "input",
        type=Path,
        nargs="?",
        help="Activities JSON file (from summarize_activity -o)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output path (default: input with _enriched suffix)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Max number of posts to enrich (for testing)",
    )
    args = parser.parse_args()
    if not args.input or not args.input.exists():
        parser.error("Input file required")
    activities = json.loads(args.input.read_text())
    enriched, count = enrich_activities(activities, limit=args.limit)
    out_path = args.output or args.input.with_name(
        args.input.stem + "_enriched" + args.input.suffix
    )
    out_path.write_text(json.dumps(enriched, indent=2))
    print(f"Enriched {count} activities, wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
