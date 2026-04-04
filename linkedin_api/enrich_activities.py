#!/usr/bin/env python3
"""
Enrich activities with post content and linked URLs.

Reads ``EnrichedRecord`` rows (from CSV via ``collect_from_csv``); writes only
to the content store.
For each activity with post_url
that has not been processed yet:

1. Persists URLs already extracted from API text (present in the activities record).
2. Fetches the post page via HTTP to obtain content (when not already stored) and
   additional URLs from the rendered page. Both sources are merged.

Content is only saved to the store when it was not already available.
URLs from API text are saved even when the HTTP fetch fails (e.g. login required).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from linkedin_api.activity_csv import get_default_csv_path
from linkedin_api.enriched_record import EnrichedRecord
from linkedin_api.content_store import (
    _ms_to_iso,
    has_metadata,
    load_content,
    save_content,
    save_metadata,
)
from linkedin_api.summarize_activity import collect_from_csv
from linkedin_api.utils.linkedin_snowflake import post_created_at_from_urn
from linkedin_api.utils.post_html import (
    linkedin_http_fetch_is_blocked,
    parse_post_body_from_soup,
    parse_post_meta_from_soup,
)
from linkedin_api.utils.urls import extract_urls_from_text, is_comment_feed_url

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs"

_FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _fetch_with_requests(url: str) -> tuple[str, list[str], dict] | None:
    """
    Try simple HTTP request. Returns (content, urls, html_meta) if successful, None on
    non-200, empty content, or error. html_meta may have post_created_at, post_author.
    """
    try:
        resp = requests.get(
            url, timeout=10, allow_redirects=True, headers=_FETCH_HEADERS
        )
        if resp.status_code != 200:
            return None
        html = resp.text
        if linkedin_http_fetch_is_blocked(resp.url, html):
            return None
        soup = BeautifulSoup(html, "html.parser")
        content = parse_post_body_from_soup(soup)
        if not content or len(content) < 50:
            return None
        html_meta = parse_post_meta_from_soup(soup)
        return content, extract_urls_from_text(content), html_meta
    except Exception:
        return None


def _run_enrichment(to_enrich: list[EnrichedRecord]):
    """
    Generator: for each record, persist URLs from API text and attempt HTTP fetch
    for post content and additional URLs. Yields (done, total) after each item.
    Returns enriched_count via StopIteration.
    """
    total = len(to_enrich)
    enriched_count = 0
    needs_browser: list[EnrichedRecord] = []

    for i, rec in enumerate(to_enrich):
        urn = rec.post_urn
        url = rec.post_url
        if urn and url:
            ts_ms = int(rec.timestamp) if rec.timestamp is not None else None
            post_created = (rec.post_created_at or "").strip() or None
            # Fallback: Snowflake ID from URN encodes creation time (no HTTP needed)
            if not post_created:
                post_created = post_created_at_from_urn(urn)
            post_author: str | None = None
            post_author_url: str | None = None
            urls_from_api = rec.urls

            # 1) Content already in store (e.g. from a previous HTTP fetch)
            stored = load_content(urn)
            if stored and len(stored) >= 50:
                if not rec.content:
                    rec.content = stored
                rec.urls = list(dict.fromkeys(urls_from_api))
                save_metadata(
                    urn,
                    urls=rec.urls,
                    post_url=url,
                    post_author=post_author or "",
                    post_author_url=post_author_url or "",
                    activity_time_iso=_ms_to_iso(ts_ms),
                    post_created_at=post_created,
                    post_urn=urn,
                    post_id=rec.post_id or "",
                    activities_ids=[rec.activity_id] if rec.activity_id else [],
                )
                enriched_count += 1
            else:
                # 2) Try HTTP fetch for content and additional URLs
                result = _fetch_with_requests(url)
                if result:
                    fetched_content, fetched_urls, html_meta = result
                    if not post_created and html_meta.get("post_created_at"):
                        post_created = html_meta["post_created_at"]
                    if html_meta.get("post_author"):
                        post_author = html_meta["post_author"]
                    if html_meta.get("post_author_url"):
                        post_author_url = html_meta["post_author_url"]
                    all_urls = list(dict.fromkeys(urls_from_api + fetched_urls))
                    rec.urls = all_urls
                    if not rec.content:
                        rec.content = fetched_content
                        save_content(urn, fetched_content)
                    save_metadata(
                        urn,
                        urls=all_urls,
                        post_url=url,
                        post_author=post_author or "",
                        post_author_url=post_author_url or "",
                        activity_time_iso=_ms_to_iso(ts_ms),
                        post_created_at=post_created,
                        post_urn=urn,
                        post_id=rec.post_id or "",
                        activities_ids=[rec.activity_id] if rec.activity_id else [],
                    )
                    enriched_count += 1
                else:
                    # CSV ``content`` is only the *post* body for activity_type=post.
                    # Repost rows carry reshare commentary; comments use ``comment_text``.
                    api_body = (rec.content or "").strip()
                    api_urls = list(dict.fromkeys(urls_from_api))
                    if rec.interaction_type == "post" and len(api_body) >= 50:
                        rec.urls = api_urls
                        save_content(urn, api_body)
                        save_metadata(
                            urn,
                            urls=api_urls,
                            post_url=url,
                            post_author=post_author or "",
                            post_author_url=post_author_url or "",
                            activity_time_iso=_ms_to_iso(ts_ms),
                            post_created_at=post_created,
                            post_urn=urn,
                            post_id=rec.post_id or "",
                            activities_ids=[rec.activity_id] if rec.activity_id else [],
                        )
                        enriched_count += 1
                    elif api_urls:
                        rec.urls = api_urls
                        save_metadata(
                            urn,
                            urls=api_urls,
                            post_url=url,
                            post_author=post_author or "",
                            post_author_url=post_author_url or "",
                            activity_time_iso=_ms_to_iso(ts_ms),
                            post_created_at=post_created,
                            post_urn=urn,
                            post_id=rec.post_id or "",
                            activities_ids=[rec.activity_id] if rec.activity_id else [],
                        )
                        enriched_count += 1
                    else:
                        needs_browser.append(rec)
        yield i + 1, total

    for rec in needs_browser:
        rec.enrich_error = "Browser required; not implemented"
    return enriched_count


def enrich_activities(
    activities: list[EnrichedRecord],
    *,
    limit: int | None = None,
) -> tuple[list[EnrichedRecord], int]:
    """
    Enrich activities that have post_url and have not been processed yet.
    Returns (enriched_activities, count_enriched).
    """
    to_enrich = [
        a
        for a in activities
        if a.post_url
        and not is_comment_feed_url(a.post_url)
        and not has_metadata(a.post_urn)
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
    activities: list[EnrichedRecord],
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
        if a.post_url
        and not is_comment_feed_url(a.post_url)
        and not has_metadata(a.post_urn)
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
        help="activities.csv path (default: master CSV)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Max number of posts to enrich (for testing)",
    )
    args = parser.parse_args()
    in_path = args.input
    if not in_path:
        in_path = get_default_csv_path()
    if not in_path.exists():
        parser.error(f"Input not found: {in_path}")
    if in_path.suffix.lower() != ".csv":
        parser.error(f"Expected a .csv file, got {in_path}")
    activities = collect_from_csv(csv_path=in_path)
    _, count = enrich_activities(activities, limit=args.limit)
    print(f"Enriched {count} activities (content store updated).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
