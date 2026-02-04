#!/usr/bin/env python3
"""Run the enrichment path (fetch + thumbnail) once and print timing from debug.log."""

import os
import sys
from pathlib import Path

# Project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from linkedin_api.enrich_profiles import (
    extract_author_profile_with_details,
    get_thumbnail_path_for_url,
)
from linkedin_api.review_store import get_work_queue


def _get_post_url_from_raw(raw: dict):
    activity = raw.get("activity") or {}
    for key in ("id", "root", "object"):
        post_urn = activity.get(key, "")
        if post_urn and isinstance(post_urn, str) and post_urn.startswith("urn:li:"):
            return f"https://www.linkedin.com/feed/update/{post_urn}"
    return None


def main():
    url = os.environ.get("TEST_POST_URL")
    if not url:
        queue = get_work_queue()
        if not queue:
            print("No work queue. Run the app, click Load, then run this script again.")
            print("Or set TEST_POST_URL=<linkedin_post_url>")
            return 1
        item = queue[0]
        preview = item.get("corrected_json") or item.get("extracted_json") or {}
        raw = item.get("raw_json") or {}
        for node in preview.get("nodes") or []:
            if node.get("label") == "Post":
                u = (node.get("properties") or {}).get("url")
                if u:
                    url = u
                    break
        if not url:
            url = _get_post_url_from_raw(raw)
        if not url:
            print("First queue item has no post URL.")
            return 1
    print("URL:", url[:80] + "..." if len(url) > 80 else url)
    print("Fetching author + content...")
    details = extract_author_profile_with_details(url)
    print(
        "Author:",
        (
            "ok"
            if details.get("author")
            else details.get("error") or details.get("skip_reason")
        ),
    )
    print("Taking thumbnail...")
    thumb = get_thumbnail_path_for_url(url)
    print("Thumbnail:", thumb or "none")
    log_path = Path(__file__).resolve().parent.parent / ".cursor" / "debug.log"
    if not log_path.exists():
        print("No debug.log found.")
        return 0
    print("\n--- Timing (debug.log) ---")
    for line in log_path.read_text().strip().splitlines():
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
