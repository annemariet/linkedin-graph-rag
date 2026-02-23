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
import sys
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

from linkedin_api.enrich_activities import (
    enrich_activities,
    enrich_activities_streaming,
)
from linkedin_api.summarize_activity import (
    _format_timestamp,
    collect_activities,
    collect_from_live,
)
from linkedin_api.summarize_posts import (
    load_from_json_and_save,
    summarize_posts,
    summarize_posts_streaming,
)

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs"
DEFAULT_ACTIVITIES = OUTPUT_DIR / "activities.json"
DEFAULT_ENRICHED = OUTPUT_DIR / "activities_enriched.json"


def _collect_activities(args) -> tuple[Path, int]:
    """Collect activities from changelog (or cache). Returns (path to activities JSON, count)."""
    from datetime import datetime, timezone

    from linkedin_api.summarize_activity import _parse_last

    last = args.last or "30d"
    start_ms = _parse_last(last)
    if start_ms is None:
        raise ValueError(f"Invalid --last '{last}'; use e.g. 7d, 14d, 30d")
    end_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    types_set = {t.strip() for t in args.types.split(",") if t.strip()}

    data = collect_from_live(
        last,
        types_set,
        verbose=not args.quiet,
        skip_fetch=args.from_cache,
    )
    if not data["nodes"] and args.from_cache:
        raise SystemExit('No changelog cache found. Run without "Skip fetch" first.')

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
    return out_path, len(records)


def _enrich_activities(activities_path: Path, args) -> tuple[Path, int]:
    """Enrich activities with content. Returns (path to enriched JSON, count)."""
    activities = json.loads(activities_path.read_text())
    enriched, count = enrich_activities(activities, limit=args.limit)
    if not args.quiet:
        print(f"Enriched {count} activities")

    out_path = Path(args.enriched_output) if args.enriched_output else DEFAULT_ENRICHED
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(enriched, indent=2))
    if not args.quiet:
        print(f"Wrote {out_path}")
    return out_path, count


def _summarize_posts(args, enriched_path: Path | None = None):
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


def _enrich_activities_streaming(activities_path: Path, args):
    """
    Generator variant of _enrich_activities.
    Yields (done, total) per activity. Returns (out_path, count) via StopIteration.
    """
    activities = json.loads(activities_path.read_text())
    gen = enrich_activities_streaming(activities, limit=args.limit)
    enriched = activities
    count = 0
    try:
        while True:
            yield next(gen)
    except StopIteration as e:
        enriched, count = e.value
    out_path = Path(args.enriched_output) if args.enriched_output else DEFAULT_ENRICHED
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(enriched, indent=2))
    return out_path, count


def _summarize_posts_streaming(args, enriched_path: Path | None = None):
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
        types="reaction,repost,comment",
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
        activities_path, _ = _collect_activities(args)
        enriched_path, _ = _enrich_activities(activities_path, args)
        _summarize_posts(args, enriched_path)
        return True, out.getvalue()
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 1
        return code == 0, out.getvalue()
    except Exception as e:
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
):
    """
    Generator that runs the MVP pipeline and yields user-friendly progress for the UI.

    Full technical output goes to the terminal (stdout). Yields only short progress
    lines so the UI stays readable.
    """
    args = SimpleNamespace(
        last=last,
        from_cache=from_cache,
        types="reaction,repost,comment",
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
        activities_path, n1 = _collect_activities(args)
        yield _add(f"Collected {n1} activities.")

        # Enrich with per-activity progress (placeholder updated in-place)
        enriched_path = DEFAULT_ENRICHED
        n2 = 0
        lines.append("Enriching…")
        gen = _enrich_activities_streaming(activities_path, args)
        try:
            while True:
                done, total = next(gen)
                lines[-1] = f"Enriching {done}/{total}…"
                yield _snapshot()
        except StopIteration as e:
            enriched_path, n2 = e.value
        lines[-1] = f"Enriched {n2} activities."
        yield _snapshot()

        # Summarize with per-batch progress (placeholder updated in-place)
        n3 = 0
        lines.append("Summarizing…")
        gen = _summarize_posts_streaming(args, enriched_path)
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
        help="Use only cached changelog data (no API fetch)",
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
    parser.add_argument("--batch-size", type=int, default=5, help="Phase 3 batch size")
    parser.add_argument("-q", "--quiet", action="store_true")
    args = parser.parse_args()

    if not args.last and not args.from_cache:
        args.from_cache = True
        args.last = "30d"
        if not args.quiet:
            print("Using --skip-fetch --last 30d (default)")

    try:
        activities_path, _ = _collect_activities(args)
        enriched_path, _ = _enrich_activities(activities_path, args)
        _summarize_posts(args, enriched_path)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 1
    except Exception as e:
        print(f"Error: {e}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
