#!/usr/bin/env python3
"""
Collect activities (reactions, reposts, comments) for period-based summarization.

- Fetch: Fetches from API, appends to activities.csv, loads with period filter.
- Skip fetch (--from-cache): Load from activities.csv only, filter by period.

Programmatic use: ``collect_from_csv`` returns activity dicts for enrich/report
downstream; this CLI only fetches and reports counts (data lives in CSV).
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from linkedin_api.activity_csv import (
    ActivityRecord,
    ActivityType,
    append_records_csv,
    filter_by_date,
    get_default_csv_path,
    load_records_csv,
)
from linkedin_api.extract_graph_data import (
    extract_activity_records,
    get_all_post_activities,
)
from linkedin_api.utils.changelog import (
    get_max_processed_at,
    save_last_processed_timestamp,
)
from linkedin_api.utils.urls import extract_urls_from_text
from linkedin_api.utils.urns import comment_urn_to_post_url, urn_to_post_url


def _urn_to_url(urn: str) -> str:
    """Resolve URN to LinkedIn URL (post or comment)."""
    if urn.startswith("urn:li:comment:"):
        return comment_urn_to_post_url(urn) or ""
    return urn_to_post_url(urn) or ""


def _format_timestamp(ts_ms: int | None) -> str:
    """Format epoch ms to ISO string."""
    if ts_ms is None:
        return ""
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S%z"
    )


def _parse_last(value: str) -> int | None:
    """Convert '7d', '14d', '30d' to start_time in epoch milliseconds."""
    if not value or len(value) < 2:
        return None
    try:
        n = int(value[:-1])
    except ValueError:
        return None
    unit = value[-1].lower()
    if unit == "d":
        delta = timedelta(days=n)
    elif unit == "w":
        delta = timedelta(weeks=n)
    elif unit == "m":
        delta = timedelta(days=n * 30)
    else:
        return None
    cutoff = datetime.now(timezone.utc) - delta
    return int(cutoff.timestamp() * 1000)


_TYPE_TO_INTERACTION: dict[str, str] = {
    ActivityType.REACTION_TO_POST.value: "reaction",
    ActivityType.REACTION_TO_COMMENT.value: "reaction",
    ActivityType.REPOST.value: "repost",
    ActivityType.INSTANT_REPOST.value: "repost",
    ActivityType.COMMENT.value: "comment",
}


def activity_record_to_activity_dict(rec: ActivityRecord) -> dict:
    """Build the activity dict used by enrich (from one CSV ``ActivityRecord``)."""
    urls = extract_urls_from_text(rec.content) if rec.content else []
    ts = int(rec.time) if rec.time else None
    interaction_type = _TYPE_TO_INTERACTION.get(rec.activity_type, "reaction")
    is_comment = rec.activity_type == ActivityType.COMMENT.value
    post_urn = rec.parent_urn or rec.activity_urn if is_comment else rec.activity_urn
    post_url = rec.post_url or _urn_to_url(post_urn)
    return {
        "post_urn": post_urn,
        "post_url": post_url,
        "content": "" if is_comment else (rec.content or ""),
        "urls": urls,
        "interaction_type": interaction_type,
        "reaction_type": rec.reaction_type or None,
        "comment_text": rec.content if is_comment else "",
        "post_id": rec.post_id,
        "activity_id": rec.activity_id,
        "timestamp": ts,
        "created_at": rec.created_at or _format_timestamp(ts),
    }


def ensure_csv_fetched(
    last: str,
    verbose: bool = True,
    skip_fetch: bool = False,
) -> int:
    """
    Fetch from API and append to activities.csv. Returns count of new records written.

    When skip_fetch is True, does nothing and returns 0.
    """
    if skip_fetch:
        return 0
    period_start = _parse_last(last)
    if period_start is None:
        raise ValueError(f"Invalid --last value; use e.g. 7d, 14d, 30d")
    if verbose:
        print("Fetching from API and appending to activities.csv...")
    elements = get_all_post_activities(start_time=period_start, verbose=verbose)
    if not elements:
        return 0
    records = extract_activity_records(elements)
    written = append_records_csv(records)
    if written and verbose:
        print(f"   Appended {written} new records to {get_default_csv_path()}")
    max_ts = get_max_processed_at(elements)
    if max_ts:
        save_last_processed_timestamp(max_ts)
    return written


def collect_from_csv(
    start: datetime | None = None,
    end: datetime | None = None,
    csv_path: Path | None = None,
) -> list[dict]:
    """
    Load activities from CSV, optional period filter, return dicts for enrich/report.
    Includes reactions, reposts, and comments.
    """
    records = load_records_csv(csv_path)
    if not records:
        return []
    if start or end:
        records = filter_by_date(records, start=start, end=end)
    return [activity_record_to_activity_dict(r) for r in records]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Collect activities for period-based summarization (reactions, reposts, comments)."
    )
    parser.add_argument(
        "--last",
        metavar="Nd",
        help="Fetch from API: last N days/weeks (e.g. 7d, 14d, 30d)",
    )
    parser.add_argument(
        "--from-cache",
        action="store_true",
        help="Skip API fetch; use only activities.csv. Use with --last to filter by period.",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Less verbose output",
    )
    args = parser.parse_args()

    if not args.last and not args.from_cache:
        parser.error("Specify --last or --from-cache")
    if args.last and not args.from_cache:
        pass  # Live API fetch
    elif args.from_cache:
        pass  # Cache; --last optional to filter within cached data

    last = args.last or "30d"
    start_dt = None
    end_dt = None
    if args.last:
        start_ms = _parse_last(args.last)
        if start_ms is None:
            parser.error(f"Invalid --last '{args.last}'; use e.g. 7d, 14d, 30d")
        start_dt = datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc)
        end_dt = datetime.now(timezone.utc)

    ensure_csv_fetched(last, verbose=not args.quiet, skip_fetch=args.from_cache)

    csv_path = get_default_csv_path()
    records = collect_from_csv(start=start_dt, end=end_dt, csv_path=csv_path)
    if not records and args.from_cache:
        print(
            "No data in activities.csv. Run extract_graph_data or use --last to fetch."
        )
        return 1
    n = len(records)
    print(f"Collected {n} activities (see {csv_path} for full data).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
