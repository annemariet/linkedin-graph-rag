#!/usr/bin/env python3
"""
Run the full MVP pipeline: collect → enrich → summarize.

Processes new data and backfills history (posts in store not yet summarized).
Use --seed-json to load existing enriched JSON into the store first.

Incremental: Running 7d then 30d avoids recomputing. Phase 1 reads the period slice
from activities.csv (optional --output JSON for debugging). Phase 2 enriches into the
content store (.md + .meta.json). Phase 3 LLM-summarizes posts that lack summary
metadata. Optional --enriched-output writes a JSON snapshot for debugging only.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

from linkedin_api.enrich_activities import (
    enrich_activities,
    enrich_activities_streaming,
)
from linkedin_api.fetch_linked_content import fetch_linked_content_streaming
from linkedin_api.activity_csv import get_default_csv_path
from linkedin_api.summarize_activity import (
    collect_from_csv,
    ensure_csv_fetched,
    summarization_record_to_activity_dict,
)
from linkedin_api.summarize_posts import (
    load_from_json_and_save,
    summarize_posts,
    summarize_posts_streaming,
)


def _collect_activities(args) -> tuple[list[dict], int]:
    """Collect activities from CSV (fetch + append when not skip-fetch). Returns (activity dicts, count)."""
    from datetime import datetime, timezone

    from linkedin_api.summarize_activity import _parse_last

    last = args.last or "30d"
    start_dt = None
    end_dt = None
    if last:
        start_ms = _parse_last(last)
        if start_ms is None:
            raise ValueError(f"Invalid --last '{last}'; use e.g. 7d, 14d, 30d")
        start_dt = datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc)
        end_dt = datetime.now(timezone.utc)

    ensure_csv_fetched(last, verbose=not args.quiet, skip_fetch=args.from_cache)

    records = collect_from_csv(
        start=start_dt, end=end_dt, csv_path=get_default_csv_path()
    )
    if not records and args.from_cache:
        raise SystemExit(
            'No data in activities.csv. Run extract_graph_data or use without "Skip fetch".'
        )

    if not args.quiet:
        print(f"Collected {len(records)} activities")

    out = [summarization_record_to_activity_dict(r) for r in records]
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(out, indent=2))
        if not args.quiet:
            print(f"Wrote debug JSON {out_path}")
    return out, len(records)


def _enrich_activities(activities: list[dict], args) -> int:
    """Enrich activities into the content store. Returns count enriched."""
    enriched, count = enrich_activities(activities, limit=args.limit)
    if not args.quiet:
        print(f"Enriched {count} activities")

    if args.enriched_output:
        out_path = Path(args.enriched_output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(enriched, indent=2))
        if not args.quiet:
            print(f"Wrote debug enriched JSON {out_path}")
    return count


def _summarize_posts(args):
    """Summarize posts in store that lack a summary (via LLM)."""
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
        if n == 0:
            print("Summarized 0 posts.")
        else:
            print(f"Summarized {n} posts.")
    return n


def _enrich_activities_streaming(activities: list[dict], args):
    """
    Generator variant of _enrich_activities.
    Yields (done, total) per activity. Returns count via StopIteration.
    """
    gen = enrich_activities_streaming(activities, limit=args.limit)
    enriched = activities
    count = 0
    try:
        while True:
            yield next(gen)
    except StopIteration as e:
        enriched, count = e.value
    if args.enriched_output:
        out_path = Path(args.enriched_output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(enriched, indent=2))
    return count


def _fetch_linked_content_streaming(args):
    """
    Generator: fetch content from URLs linked in posts. Yields (done, total).
    Returns urls_fetched via StopIteration.
    """
    gen = fetch_linked_content_streaming(limit=args.limit, skip_cached=True)
    try:
        while True:
            yield next(gen)
    except StopIteration as e:
        return e.value or 0


def _summarize_posts_streaming(args, summary_provider=None, summary_model=None):
    """
    Generator variant of _summarize_posts.
    Yields (batches_done, total_batches) per batch. Returns total via StopIteration.
    """
    if args.seed_json:
        p = Path(args.seed_json)
        if p.exists():
            n = load_from_json_and_save(p)
            if not args.quiet:
                print(f"Seeded store from {p}: {n} posts")
    gen = summarize_posts_streaming(
        limit=args.limit,
        batch_size=args.batch_size,
        quiet=args.quiet,
        llm_provider=summary_provider,
        llm_model=summary_model,
    )
    try:
        while True:
            yield next(gen)
    except StopIteration as e:
        return e.value or 0


def run_pipeline_ui(
    last: str = "7d",
    from_cache: bool = False,
    limit: int | None = None,
    batch_size: int = 5,
    seed_json: str | None = None,
) -> tuple[bool, str]:
    """
    Run the MVP pipeline with given options; capture stdout and return (success, log).

    For use from Gradio or other UIs. Does not call sys.exit.
    """
    args = SimpleNamespace(
        last=last,
        from_cache=from_cache,
        output=None,
        enriched_output=None,
        seed_json=seed_json,
        limit=limit,
        batch_size=batch_size,
        quiet=False,
    )
    if not args.last and not args.from_cache:
        args.from_cache = True
        args.last = "30d"
    out = StringIO()
    old_stdout = sys.stdout
    try:
        sys.stdout = out
        activities, _ = _collect_activities(args)
        _enrich_activities(activities, args)
        for _ in _fetch_linked_content_streaming(args):
            pass  # exhaust generator
        _summarize_posts(args)
        return True, out.getvalue()
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 1
        return code == 0, out.getvalue()
    except Exception as e:
        traceback.print_exc(file=out)
        print(f"Error: {e}", file=out)
        return False, out.getvalue()
    finally:
        sys.stdout = old_stdout


def run_pipeline_ui_streaming(
    last: str = "7d",
    from_cache: bool = False,
    limit: int | None = None,
    batch_size: int = 5,
    seed_json: str | None = None,
    summary_provider: str | None = None,
    summary_model: str | None = None,
):
    """
    Generator that runs the MVP pipeline and yields user-friendly progress for the UI.

    Full technical output goes to the terminal (stdout). Yields only short progress
    lines so the UI stays readable.
    """
    args = SimpleNamespace(
        last=last,
        from_cache=from_cache,
        output=None,
        enriched_output=None,
        seed_json=seed_json,
        limit=limit,
        batch_size=batch_size,
        quiet=False,
    )
    if not args.last and not args.from_cache:
        args.from_cache = True
        args.last = "30d"
    lines: list[str] = []

    def _snapshot() -> str:
        return "\n".join(lines)

    def _add(msg: str) -> str:
        lines.append(msg)
        return _snapshot()

    try:
        yield _add("Starting pipeline…")
        activities, n1 = _collect_activities(args)
        yield _add(f"Collected {n1} activities.")

        # Enrich with per-activity progress (placeholder updated in-place)
        n2 = 0
        lines.append("Enriching…")
        gen = _enrich_activities_streaming(activities, args)
        try:
            while True:
                done, total = next(gen)
                lines[-1] = f"Enriching {done}/{total}…"
                yield _snapshot()
        except StopIteration as e:
            n2 = e.value
        lines[-1] = f"Enriched {n2} activities."
        yield _snapshot()

        # Fetch linked URL content (posts with urls in metadata)
        n_urls = 0
        lines.append("Fetching linked URLs…")
        gen = _fetch_linked_content_streaming(args)
        try:
            while True:
                done, total = next(gen)
                lines[-1] = f"Fetching linked URLs {done}/{total}…"
                yield _snapshot()
        except StopIteration as e:
            n_urls = e.value or 0
        lines[-1] = f"Fetched {n_urls} URL(s) from linked posts."
        yield _snapshot()

        # Summarize with per-batch progress (placeholder updated in-place)
        n3 = 0
        lines.append("Summarizing…")
        gen = _summarize_posts_streaming(
            args,
            summary_provider=summary_provider,
            summary_model=summary_model,
        )
        try:
            while True:
                batches_done, total_batches = next(gen)
                lines[-1] = f"Summarizing batch {batches_done}/{total_batches}…"
                yield _snapshot()
        except StopIteration as e:
            n3 = e.value or 0
        lines[-1] = f"Summarized {n3} posts."
        yield _snapshot()

        yield _add("✅ Done.")
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 1
        yield _add(f"❌ Failed (exit {code}).")
    except Exception as e:
        traceback.print_exc()
        yield _add(f"❌ Failed: {e}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run MVP pipeline: collect → enrich → summarize (including history)."
    )
    parser.add_argument("--last", metavar="Nd", help="Period: 7d, 14d, 30d")
    parser.add_argument(
        "--skip-fetch",
        action="store_true",
        dest="from_cache",
        help="Use only cached data from activities.csv (no API fetch)",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Optional: write Phase 1 activity JSON for debugging (default: no file)",
    )
    parser.add_argument(
        "--enriched-output",
        help="Optional: write Phase 2 enriched activity JSON for debugging",
    )
    parser.add_argument(
        "--seed-json",
        metavar="PATH",
        help="Load enriched JSON into store first (for history backfill)",
    )
    parser.add_argument("--limit", type=int, help="Limit posts per phase")
    parser.add_argument("--batch-size", type=int, default=5, help="Phase 3 batch size")
    parser.add_argument("-q", "--quiet", action="store_true")
    args = parser.parse_args()

    if not args.last and not args.from_cache:
        args.from_cache = True
        args.last = "30d"
        if not args.quiet:
            print("Using --skip-fetch --last 30d (default)")

    try:
        activities, _ = _collect_activities(args)
        _enrich_activities(activities, args)
        for _ in _fetch_linked_content_streaming(args):
            pass
        _summarize_posts(args)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 1
    except Exception as e:
        print(f"Error: {e}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
