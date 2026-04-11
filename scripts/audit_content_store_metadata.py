#!/usr/bin/env python3
"""
Report how often content-store sidecars have fields we expect from enrichment / HTML.

Scans ``<data_dir>/content/*.meta.json`` and optionally joins ``activities.csv`` for
comment-activity context (comment text lives in CSV; post author URLs come from HTML
into ``.meta.json`` — we do **not** persist per-comment author names in metadata).

Examples::

    uv run python scripts/audit_content_store_metadata.py
    uv run python scripts/audit_content_store_metadata.py --verbose --list-missing post_author
    uv run python scripts/audit_content_store_metadata.py --csv ~/.linkedin_api/data/activities.csv
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

# Allow ``python scripts/...`` without PYTHONPATH.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from linkedin_api.activity_csv import (  # noqa: E402
    ActivityType,
    get_data_dir,
    load_records_csv,
)


def _content_dir(data_dir: Path | None) -> Path:
    base = data_dir if data_dir is not None else get_data_dir()
    return base / "content"


def _load_registry(content_dir: Path) -> dict[str, str]:
    p = content_dir / "_urn_registry.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def _non_empty_str(v) -> bool:
    return bool(v and str(v).strip())


def _non_empty_list(v) -> bool:
    return isinstance(v, list) and len(v) > 0


def _audit_meta_files(content_dir: Path) -> tuple[list[dict], int]:
    """Return (per-file records, total meta files on disk)."""
    registry = _load_registry(content_dir)
    paths = sorted(content_dir.glob("*.meta.json"))
    out: list[dict] = []
    for path in paths:
        stem = path.stem.removesuffix(".meta")
        try:
            meta: dict = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        urn = (registry.get(stem) or meta.get("post_urn") or "").strip()
        out.append(
            {
                "stem": stem,
                "path": path,
                "urn": urn,
                "meta": meta,
                "has_urls": _non_empty_list(meta.get("urls")),
                "has_post_author": _non_empty_str(meta.get("post_author")),
                "has_post_author_url": _non_empty_str(meta.get("post_author_url")),
                "has_post_created_at": _non_empty_str(meta.get("post_created_at")),
                "has_post_url": _non_empty_str(meta.get("post_url")),
                "has_post_urn": _non_empty_str(meta.get("post_urn")),
                "has_post_id": _non_empty_str(meta.get("post_id")),
                "has_activities_ids": _non_empty_list(meta.get("activities_ids")),
                "has_summary": _non_empty_str(meta.get("summary")),
            }
        )
    return out, len(paths)


def _csv_comment_stats(csv_path: Path, post_ids: set[str]) -> dict:
    """Counts for comment rows whose post_id appears in enriched metadata."""
    records = load_records_csv(csv_path)
    comments_on_tracked_posts = 0
    comments_with_text = 0
    total_comments = 0
    for r in records:
        if r.activity_type != ActivityType.COMMENT.value:
            continue
        total_comments += 1
        pid = (r.post_id or "").strip()
        if pid not in post_ids:
            continue
        comments_on_tracked_posts += 1
        if (r.content or "").strip():
            comments_with_text += 1
    return {
        "total_comment_rows": total_comments,
        "comments_on_enriched_post_ids": comments_on_tracked_posts,
        "those_with_non_empty_content": comments_with_text,
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Audit .meta.json fill rates (HTML-oriented vs LLM summary).",
    )
    ap.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Override LINKEDIN_DATA_DIR parent (default: get_data_dir())",
    )
    ap.add_argument(
        "--csv",
        type=Path,
        default=None,
        help="activities.csv for optional comment-row stats vs enriched post_ids",
    )
    ap.add_argument(
        "--list-missing",
        choices=("post_author", "post_author_url", "urls", "all_html"),
        default=None,
        help="Print stems (first column) missing the given field(s)",
    )
    ap.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-file stem + booleans",
    )
    ap.add_argument("--json", action="store_true", help="Machine-readable summary")
    args = ap.parse_args()

    data_root = args.data_dir
    if data_root is not None:
        content_dir = data_root / "content"
    else:
        content_dir = _content_dir(None)

    if not content_dir.is_dir():
        print(f"Content directory not found: {content_dir}", file=sys.stderr)
        return 1

    rows, raw_meta_count = _audit_meta_files(content_dir)
    n = len(rows)
    if n == 0:
        print(f"No readable *.meta.json under {content_dir}")
        return 0

    def pct(k: str) -> float:
        return 100.0 * sum(1 for r in rows if r[k]) / n if n else 0.0

    keys_html = (
        "has_urls",
        "has_post_author",
        "has_post_author_url",
        "has_post_created_at",
        "has_post_url",
        "has_post_urn",
        "has_post_id",
        "has_activities_ids",
    )
    summary = {
        "content_dir": str(content_dir),
        "meta_files_readable": n,
        "meta_files_glob": raw_meta_count,
        "pct": {k.replace("has_", ""): round(pct(k), 1) for k in keys_html},
        "pct_summary": round(pct("has_summary"), 1),
    }

    if args.json:
        extra = {}
        if args.csv and args.csv.exists():
            pids = {r["meta"].get("post_id", "") for r in rows}
            pids = {p for p in pids if p}
            extra["csv_comment_stats"] = _csv_comment_stats(args.csv, pids)
        print(json.dumps({**summary, **extra}, indent=2))
        return 0

    print(f"Content dir: {content_dir}")
    print(f"Readable .meta.json files: {n} (glob count: {raw_meta_count})\n")
    print("Fields typically filled from HTML enrichment (or merged URLs):")
    for k in keys_html:
        label = k.replace("has_", "")
        c = sum(1 for r in rows if r[k])
        print(f"  {label:22} {c:4}/{n}  ({pct(k):5.1f}%)")
    print()
    n_sum = sum(1 for r in rows if r["has_summary"])
    print(
        f"LLM phase (summarize_posts): summary non-empty: "
        f"{n_sum:4}/{n}  ({pct('has_summary'):5.1f}%)"
    )

    if args.csv:
        if not args.csv.exists():
            print(f"\nCSV not found: {args.csv}", file=sys.stderr)
            return 1
        pids = {(r["meta"].get("post_id") or "").strip() for r in rows}
        pids.discard("")
        st = _csv_comment_stats(args.csv, pids)
        print()
        print("CSV comment rows (API text; not HTML author names in .meta.json):")
        print(f"  Total comment rows in CSV: {st['total_comment_rows']}")
        print(
            f"  Comments on a post_id that appears in metadata: "
            f"{st['comments_on_enriched_post_ids']}"
        )
        print(
            f"  Those with non-empty comment text: {st['those_with_non_empty_content']}"
        )
        print(
            "\nNote: per-comment author is not stored in .meta.json; see CSV "
            "author_urn / comment text. Post author name+URL are HTML → metadata."
        )

    if args.list_missing:
        print()
        print(f"--- Missing {args.list_missing} (stem) ---")
        for r in rows:
            m = args.list_missing
            if m == "all_html":
                miss = not (
                    r["has_urls"] and r["has_post_author"] and r["has_post_author_url"]
                )
            elif m == "post_author":
                miss = not r["has_post_author"]
            elif m == "post_author_url":
                miss = not r["has_post_author_url"]
            else:
                miss = not r["has_urls"]
            if miss:
                print(r["stem"])

    if args.verbose:
        print()
        print("--- Per file ---")
        for r in rows:
            print(
                r["stem"],
                "urls" if r["has_urls"] else "-urls",
                "author" if r["has_post_author"] else "-author",
                "a_url" if r["has_post_author_url"] else "-a_url",
                "created" if r["has_post_created_at"] else "-created",
                "sum" if r["has_summary"] else "-sum",
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
