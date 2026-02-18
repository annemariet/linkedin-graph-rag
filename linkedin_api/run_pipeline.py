#!/usr/bin/env python3
"""
Run the full MVP pipeline: collect → enrich → summarize.

Processes new data and backfills history (posts in store not yet summarized).
Use --seed-json to load existing enriched JSON into the store first.

Incremental: Running 7d then 30d avoids recomputing. Phase 2 uses content store
before fetching; Phase 3 only summarizes posts that lack metadata. Output JSON
files are overwritten with the current period; the content store is appended/updated.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from linkedin_api.enrich_activities import enrich_activities
from linkedin_api.summarize_activity import (
    _format_timestamp,
    collect_activities,
    collect_from_live,
    load_from_cache,
)
from linkedin_api.summarize_posts import load_from_json_and_save, summarize_posts

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs"
DEFAULT_ACTIVITIES = OUTPUT_DIR / "activities.json"
DEFAULT_ENRICHED = OUTPUT_DIR / "activities_enriched.json"


def _run_phase1(args) -> Path:
    """Phase 1: collect activities. Returns path to activities JSON."""
    from datetime import datetime, timezone

    from linkedin_api.summarize_activity import _parse_last

    start_ms = None
    end_ms = None
    cache_start = None
    cache_end = None
    last = args.last or "30d"
    start_ms = _parse_last(last)
    if start_ms is None:
        raise ValueError(f"Invalid --last '{last}'; use e.g. 7d, 14d, 30d")
    end_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    if args.from_cache:
        cache_start, cache_end = start_ms, end_ms

    if args.from_cache:
        data = load_from_cache(start_ms=cache_start, end_ms=cache_end)
        if not data["nodes"]:
            raise SystemExit("No cached neo4j_data_*.json found. Run extraction first.")
        if not args.quiet:
            print(f"Loaded {len(data['nodes'])} nodes from cache")
    else:
        types_set = {t.strip() for t in args.types.split(",") if t.strip()}
        data = collect_from_live(last, types_set, verbose=not args.quiet)

    types_set = {t.strip() for t in args.types.split(",") if t.strip()}
    records = collect_activities(
        data, types=types_set, start_ms=start_ms, end_ms=end_ms
    )
    if not args.quiet:
        print(f"Collected {len(records)} activities")

    out_path = Path(args.output) if args.output else DEFAULT_ACTIVITIES
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out = [
        {
            "post_urn": r.post_urn,
            "post_url": r.post_url,
            "content": r.content,
            "urls": r.urls,
            "interaction_type": r.interaction_type,
            "reaction_type": r.reaction_type,
            "comment_text": r.comment_text,
            "timestamp": r.timestamp,
            "created_at": _format_timestamp(r.timestamp),
        }
        for r in records
    ]
    out_path.write_text(json.dumps(out, indent=2))
    if not args.quiet:
        print(f"Wrote {out_path}")
    return out_path


def _run_phase2(activities_path: Path, args) -> Path:
    """Phase 2: enrich. Returns path to enriched JSON."""
    activities = json.loads(activities_path.read_text())

    if not args.no_browser:
        enriched, count = enrich_activities(
            activities,
            limit=args.limit,
            use_browser=True,
            wait_s=args.wait,
            progress=not args.quiet,
        )
        if not args.quiet:
            print(f"Enriched {count} activities")
    else:
        enriched = activities
        if not args.quiet:
            print("Skipped enrichment (--no-browser)")

    out_path = Path(args.enriched_output) if args.enriched_output else DEFAULT_ENRICHED
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(enriched, indent=2))
    if not args.quiet:
        print(f"Wrote {out_path}")
    return out_path


def _run_phase3(args, enriched_path: Path | None = None):
    """Phase 3: summarize all posts in store needing summary."""
    if args.seed_json:
        p = Path(args.seed_json)
        if p.exists():
            n = load_from_json_and_save(p)
            if not args.quiet:
                print(f"Seeded store from {p}: {n} posts")
    n = summarize_posts(
        limit=args.limit,
        batch_size=args.batch_size,
        quiet=args.quiet,
    )
    if not args.quiet:
        print(f"Summarized {n} posts")
    return n


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run MVP pipeline: collect → enrich → summarize (including history)."
    )
    parser.add_argument("--last", metavar="Nd", help="Period: 7d, 14d, 30d")
    parser.add_argument(
        "--from-cache", action="store_true", help="Use cached neo4j_data"
    )
    parser.add_argument(
        "--types",
        default="reaction,repost,comment",
        help="Activity types (default: reaction,repost,comment)",
    )
    parser.add_argument("--output", "-o", help="Phase 1 output path")
    parser.add_argument("--enriched-output", help="Phase 2 output path")
    parser.add_argument(
        "--seed-json",
        metavar="PATH",
        help="Load enriched JSON into store first (for history backfill)",
    )
    parser.add_argument("--limit", type=int, help="Limit posts per phase")
    parser.add_argument(
        "--no-browser", action="store_true", help="Skip Phase 2 enrichment"
    )
    parser.add_argument("--wait", type=float, default=3.5, help="Page load wait (s)")
    parser.add_argument("--batch-size", type=int, default=5, help="Phase 3 batch size")
    parser.add_argument("-q", "--quiet", action="store_true")
    args = parser.parse_args()

    if not args.last and not args.from_cache:
        args.from_cache = True
        args.last = "30d"
        if not args.quiet:
            print("Using --from-cache --last 30d (default)")

    try:
        activities_path = _run_phase1(args)
        enriched_path = _run_phase2(activities_path, args)
        _run_phase3(args, enriched_path)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 1
    except Exception as e:
        print(f"Error: {e}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
