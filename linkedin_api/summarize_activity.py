#!/usr/bin/env python3
"""
Collect activities (reactions, reposts, comments) for period-based summarization.

- Fetch: Fetches from API, appends to activities.csv, loads with period filter.
- Skip fetch (--from-cache): Load from activities.csv only, filter by period.

Output: list of {post_urn, post_url, content, urls, interaction_type, created_at, ...}
for summarization and linked-resource pipelines.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from linkedin_api.activity_csv import (
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
from linkedin_api.extract_resources import extract_urls_from_text
from linkedin_api.utils.changelog import (
    get_max_processed_at,
    save_last_processed_timestamp,
)
from linkedin_api.utils.urns import comment_urn_to_post_url, urn_to_post_url

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs"


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


@dataclass
class SummarizationRecord:
    """Single activity (reaction, repost, or comment) for summarization output."""

    post_urn: str
    content: str
    urls: list[str]
    interaction_type: Literal["reaction", "repost", "comment"]
    timestamp: int | None
    comment_text: str = ""
    comment_urn: str = ""
    reaction_type: str | None = None
    post_url: str = ""
    post_id: str = ""
    activity_id: str = ""
    created_at: str = ""


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


_TYPE_TO_INTERACTION: dict[str, Literal["reaction", "repost", "comment"]] = {
    ActivityType.REACTION_TO_POST.value: "reaction",
    ActivityType.REACTION_TO_COMMENT.value: "reaction",
    ActivityType.REPOST.value: "repost",
    ActivityType.INSTANT_REPOST.value: "repost",
    ActivityType.COMMENT.value: "comment",
}


def _to_summarization_record(rec) -> SummarizationRecord:
    """Convert ActivityRecord to SummarizationRecord."""
    urls = extract_urls_from_text(rec.content) if rec.content else []
    ts = int(rec.time) if rec.time else None
    interaction_type = _TYPE_TO_INTERACTION.get(rec.activity_type, "reaction")
    is_comment = rec.activity_type == ActivityType.COMMENT.value
    # For comments, post_urn/post_url point to the post being commented on
    post_urn = rec.parent_urn or rec.activity_urn if is_comment else rec.activity_urn
    post_url = rec.post_url or _urn_to_url(post_urn)
    return SummarizationRecord(
        post_urn=post_urn,
        content="" if is_comment else (rec.content or ""),
        urls=urls,
        interaction_type=interaction_type,
        timestamp=ts,
        comment_text=rec.content if is_comment else "",
        comment_urn=rec.activity_urn if is_comment else "",
        reaction_type=rec.reaction_type or None,
        post_url=post_url,
        post_id=rec.post_id,
        activity_id=rec.activity_id,
        created_at=rec.created_at,
    )


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
    types: set[Literal["reaction", "repost", "comment"]],
    start: datetime | None = None,
    end: datetime | None = None,
    csv_path: Path | None = None,
) -> list[SummarizationRecord]:
    """
    Load activities from CSV, filter by period and type, convert to summarization format.
    """
    records = load_records_csv(csv_path)
    if not records:
        return []
    if start or end:
        records = filter_by_date(records, start=start, end=end)
    type_filters: set[str] = set()
    if "reaction" in types:
        type_filters.update(
            [
                ActivityType.REACTION_TO_POST.value,
                ActivityType.REACTION_TO_COMMENT.value,
            ]
        )
    if "repost" in types:
        type_filters.update(
            [ActivityType.REPOST.value, ActivityType.INSTANT_REPOST.value]
        )
    if "comment" in types:
        type_filters.add(ActivityType.COMMENT.value)
    if type_filters:
        records = [r for r in records if r.activity_type in type_filters]
    return [_to_summarization_record(r) for r in records]


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
        "--types",
        default="reaction,repost,comment",
        help="Comma-separated: reaction, repost, comment (default: all)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Write JSON output to file",
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

    types_set = {t.strip() for t in args.types.split(",") if t.strip()}
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
    records = collect_from_csv(
        types=types_set, start=start_dt, end=end_dt, csv_path=csv_path
    )
    if not records and args.from_cache:
        print(
            "No data in activities.csv. Run extract_graph_data or use --last to fetch."
        )
        return 1
    print(f"Collected {len(records)} activities")

    out = [
        {
            "post_urn": r.post_urn,
            "post_url": r.post_url,
            "content": r.content,
            "urls": r.urls,
            "interaction_type": r.interaction_type,
            "reaction_type": r.reaction_type,
            "comment_text": r.comment_text,
            "post_id": r.post_id,
            "activity_id": r.activity_id,
            "timestamp": r.timestamp,
            "created_at": r.created_at or _format_timestamp(r.timestamp),
        }
        for r in records
    ]
    if args.output:
        args.output.write_text(json.dumps(out, indent=2))
        print(f"Wrote {args.output}")
    else:
        print(json.dumps(out[:5], indent=2))
        if len(out) > 5:
            print(f"... and {len(out) - 5} more")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
