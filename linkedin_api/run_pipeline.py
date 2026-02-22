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

from linkedin_api.enrich_activities import enrich_activities
from linkedin_api.summarize_activity import (
    _format_timestamp,
    collect_activities,
    collect_from_live,
)
from linkedin_api.summarize_posts import load_from_json_and_save, summarize_posts

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs"
DEFAULT_ACTIVITIES = OUTPUT_DIR / "activities.json"
DEFAULT_ENRICHED = OUTPUT_DIR / "activities_enriched.json"


def _run_phase1(args) -> Path:
    """Phase 1: collect activities (changelog cache; fetch new or skip fetch). Returns path to activities JSON."""
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
    return out_path


def _run_phase2(activities_path: Path, args) -> Path:
    """Phase 2: enrich. Returns path to enriched JSON."""
    activities = json.loads(activities_path.read_text())
    enriched, count = enrich_activities(activities, limit=args.limit)
    if not args.quiet:
        print(f"Enriched {count} activities")

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
        if n == 0:
            print("Summarized 0 posts.")
        else:
            print(f"Summarized {n} posts.")
    return n


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
        activities_path = _run_phase1(args)
        enriched_path = _run_phase2(activities_path, args)
        _run_phase3(args, enriched_path)
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
    Generator that runs the MVP pipeline and yields accumulated log after each phase.

    For use from Gradio or other UIs that support streaming output.
    Yields: str (accumulated log so far). Final yield may be prefixed with "✅ Done.\n\n" or "❌ Failed.\n\n".
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
    acc: list[str] = []
    old_stdout = sys.stdout

    def flush() -> str:
        return "\n".join(acc)

    try:
        acc.append(
            f"Starting pipeline (period={args.last}, from_cache={args.from_cache}, limit={args.limit})…"
        )
        yield flush()

        out = StringIO()
        sys.stdout = out
        activities_path = _run_phase1(args)
        acc.append(out.getvalue().strip())
        yield flush()

        out = StringIO()
        sys.stdout = out
        enriched_path = _run_phase2(activities_path, args)
        acc.append(out.getvalue().strip())
        yield flush()

        out = StringIO()
        sys.stdout = out
        _run_phase3(args, enriched_path)
        acc.append(out.getvalue().strip())
        yield "✅ Done.\n\n" + flush()
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 1
        acc.append(f"Exited with code {code}")
        yield "❌ Failed.\n\n" + flush()
    except Exception as e:
        acc.append(f"Error: {e}")
        yield "❌ Failed.\n\n" + flush()
    finally:
        sys.stdout = old_stdout


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
