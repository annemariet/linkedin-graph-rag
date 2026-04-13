#!/usr/bin/env python3
"""
Enrich activities with post content and structured metadata.

Pipeline per row (CSV → ``EnrichedRecord``):

1. If no ``.meta.json`` yet: GET ``post_url``, parse HTML via
   :mod:`linkedin_api.post_extraction` — DOM-classified ``urls`` / ``mentions`` /
   ``tags``, ``images``, trafilatura markdown (fallback: BS markdown / plain),
   JSON-LD author. Merge URL list from CSV text. Write ``.md`` + ``.meta.json``.
2. If content exists but metadata missing: classify from stored body + CSV URLs.

Comments / Playwright are not implemented (see ticket backlog).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import requests

from linkedin_api.activity_csv import get_default_csv_path
from linkedin_api.enriched_record import EnrichedRecord
from linkedin_api.content_store import (
    _ms_to_iso,
    has_metadata,
    load_content,
    resolve_urls_for_metadata,
    save_content,
    save_metadata,
)
from linkedin_api.post_extraction import (
    append_missing_resource_urls,
    extract_post_from_html,
    merge_classification_with_api,
)
from linkedin_api.summarize_activity import collect_from_csv
from linkedin_api.utils.linkedin_snowflake import post_created_at_from_urn
from linkedin_api.utils.post_html import linkedin_http_fetch_is_blocked
from linkedin_api.utils.urls import (
    extract_classified_links,
    extract_urls_from_text,
    is_comment_feed_url,
)

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs"

_FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _fetch_html(url: str) -> tuple[str, str] | None:
    try:
        resp = requests.get(
            url, timeout=10, allow_redirects=True, headers=_FETCH_HEADERS
        )
    except OSError:
        return None
    if resp.status_code != 200:
        return None
    if linkedin_http_fetch_is_blocked(resp.url, resp.text):
        return None
    return resp.text, resp.url or url


def _run_enrichment(to_enrich: list[EnrichedRecord]):
    total = len(to_enrich)
    enriched_count = 0
    needs_browser: list[EnrichedRecord] = []

    for i, rec in enumerate(to_enrich):
        urn = rec.post_urn
        url = rec.post_url
        if urn and url:
            ts_ms = int(rec.timestamp) if rec.timestamp is not None else None
            post_created = (rec.post_created_at or "").strip() or None
            if not post_created:
                post_created = post_created_at_from_urn(urn)
            post_author: str | None = None
            post_author_url: str | None = None
            urls_from_api = rec.urls

            stored = load_content(urn)
            if stored and len(stored) >= 50:
                if not rec.content:
                    rec.content = stored
                u2, m2, t2 = extract_classified_links(stored, urls_from_api)
                meta_urls = resolve_urls_for_metadata(u2)
                rec.urls = meta_urls
                save_metadata(
                    urn,
                    urls=meta_urls,
                    mentions=m2,
                    tags=t2,
                    post_url=url,
                    post_author=post_author or "",
                    post_author_url=post_author_url or "",
                    activity_time_iso=_ms_to_iso(ts_ms),
                    post_created_at=post_created or "",
                    post_urn=urn,
                    post_id=rec.post_id or "",
                    activities_ids=[rec.activity_id] if rec.activity_id else [],
                )
                enriched_count += 1
            else:
                fetched = _fetch_html(url)
                if fetched:
                    html, final_url = fetched
                    ext = extract_post_from_html(html, final_url)
                    if ext:
                        u, m, t = merge_classification_with_api(
                            ext.urls, ext.mentions, ext.tags, urls_from_api
                        )
                        meta_urls = resolve_urls_for_metadata(u)
                        body = append_missing_resource_urls(
                            ext.markdown_body, meta_urls
                        )
                        rec.urls = meta_urls
                        if not rec.content:
                            rec.content = body
                            save_content(urn, body)
                        if ext.html_meta.get("post_created_at") and not post_created:
                            post_created = ext.html_meta["post_created_at"]
                        post_author = ext.html_meta.get("post_author")
                        post_author_url = ext.html_meta.get("post_author_url")
                        save_metadata(
                            urn,
                            urls=meta_urls,
                            mentions=m,
                            tags=t,
                            images=ext.image_urls,
                            post_url=url,
                            post_author=post_author or "",
                            post_author_url=post_author_url or "",
                            activity_time_iso=_ms_to_iso(ts_ms),
                            post_created_at=post_created or "",
                            post_urn=urn,
                            post_id=rec.post_id or "",
                            activities_ids=[rec.activity_id] if rec.activity_id else [],
                        )
                        enriched_count += 1
                    else:
                        api_body = (rec.content or "").strip()
                        api_urls = list(dict.fromkeys(urls_from_api))
                        if rec.interaction_type == "post" and len(api_body) >= 50:
                            u, m, t = merge_classification_with_api(
                                [], [], [], api_urls
                            )
                            u, m, t = merge_classification_with_api(
                                u, m, t, extract_urls_from_text(api_body)
                            )
                            meta_urls = resolve_urls_for_metadata(u)
                            body = append_missing_resource_urls(api_body, meta_urls)
                            rec.urls = meta_urls
                            save_content(urn, body)
                            save_metadata(
                                urn,
                                urls=meta_urls,
                                mentions=m,
                                tags=t,
                                post_url=url,
                                post_author=post_author or "",
                                post_author_url=post_author_url or "",
                                activity_time_iso=_ms_to_iso(ts_ms),
                                post_created_at=post_created or "",
                                post_urn=urn,
                                post_id=rec.post_id or "",
                                activities_ids=(
                                    [rec.activity_id] if rec.activity_id else []
                                ),
                            )
                            enriched_count += 1
                        elif api_urls:
                            u, m, t = merge_classification_with_api(
                                [], [], [], api_urls
                            )
                            meta_urls = resolve_urls_for_metadata(u)
                            rec.urls = meta_urls
                            save_metadata(
                                urn,
                                urls=meta_urls,
                                mentions=m,
                                tags=t,
                                post_url=url,
                                post_author=post_author or "",
                                post_author_url=post_author_url or "",
                                activity_time_iso=_ms_to_iso(ts_ms),
                                post_created_at=post_created or "",
                                post_urn=urn,
                                post_id=rec.post_id or "",
                                activities_ids=(
                                    [rec.activity_id] if rec.activity_id else []
                                ),
                            )
                            enriched_count += 1
                        else:
                            needs_browser.append(rec)
                else:
                    api_body = (rec.content or "").strip()
                    api_urls = list(dict.fromkeys(urls_from_api))
                    if rec.interaction_type == "post" and len(api_body) >= 50:
                        u, m, t = merge_classification_with_api([], [], [], api_urls)
                        u, m, t = merge_classification_with_api(
                            u, m, t, extract_urls_from_text(api_body)
                        )
                        meta_urls = resolve_urls_for_metadata(u)
                        body = append_missing_resource_urls(api_body, meta_urls)
                        rec.urls = meta_urls
                        save_content(urn, body)
                        save_metadata(
                            urn,
                            urls=meta_urls,
                            mentions=m,
                            tags=t,
                            post_url=url,
                            post_author=post_author or "",
                            post_author_url=post_author_url or "",
                            activity_time_iso=_ms_to_iso(ts_ms),
                            post_created_at=post_created or "",
                            post_urn=urn,
                            post_id=rec.post_id or "",
                            activities_ids=[rec.activity_id] if rec.activity_id else [],
                        )
                        enriched_count += 1
                    elif api_urls:
                        u, m, t = merge_classification_with_api([], [], [], api_urls)
                        meta_urls = resolve_urls_for_metadata(u)
                        rec.urls = meta_urls
                        save_metadata(
                            urn,
                            urls=meta_urls,
                            mentions=m,
                            tags=t,
                            post_url=url,
                            post_author=post_author or "",
                            post_author_url=post_author_url or "",
                            activity_time_iso=_ms_to_iso(ts_ms),
                            post_created_at=post_created or "",
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
