#!/usr/bin/env python3
"""
Backfill content-store ``.meta.json`` with identity fields from CSV and optionally post author from HTML.

**Why:** ``linkedin_api -m linkedin_api.enrich_activities`` skips rows that already have metadata
(``has_metadata``), so older sidecars never received ``post_id``, ``post_urn``, ``activities_ids``,
or HTML-derived ``post_author``.

**Modes**

1. **CSV only (default, no LinkedIn HTTP):** For each post URN that has a ``.meta.json``, merge
   ``post_id``, ``post_urn``, and union ``activities_ids`` from all CSV rows that map to that URN
   (same canonical key as ``EnrichedRecord``).

2. **Optional author fetch:** One GET per distinct ``post_url`` that still lacks ``post_author`` after
   CSV merge, with ``--sleep`` between requests (default 1.0s). Uses the same HTML parsing as enrich;
   skips login/signup shells.

Examples::

    # Safe: no network
    uv run python scripts/backfill_content_metadata.py

    uv run python scripts/backfill_content_metadata.py \\
        --csv ~/.linkedin_api/data/activities.csv --dry-run

    # Light HTTP: only rows missing author, 1s between GETs
    uv run python scripts/backfill_content_metadata.py --fetch-author --sleep 1.0 --limit 50

    # More detail on stderr (per-file merges, each author GET)
    uv run python scripts/backfill_content_metadata.py -v --fetch-author --progress-every 50
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from linkedin_api.activity_csv import get_data_dir, load_records_csv  # noqa: E402
from linkedin_api.content_store import (  # noqa: E402
    load_metadata,
    merge_post_identity,
    update_metadata_fields,
)
from linkedin_api.enriched_record import EnrichedRecord  # noqa: E402
from linkedin_api.utils.post_html import (  # noqa: E402
    linkedin_http_fetch_is_blocked,
    parse_post_meta_from_soup,
)
from linkedin_api.utils.urns import extract_urn_id  # noqa: E402
from linkedin_api.utils.urls import is_comment_feed_url  # noqa: E402

logger = logging.getLogger("backfill_content_metadata")

_FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _load_registry(content_dir: Path) -> dict[str, str]:
    p = content_dir / "_urn_registry.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def _aggregate_csv_by_post_urn(csv_path: Path) -> tuple[dict[str, list[str]], int]:
    """Map canonical post URN -> list of activity_id from CSV (dedupe order preserved)."""
    records = load_records_csv(csv_path)
    n_rows = len(records)
    by_urn: dict[str, list[str]] = {}
    for rec in records:
        er = EnrichedRecord.from_activity_record(rec)
        urn = (er.post_urn or "").strip()
        if not urn:
            continue
        aid = (rec.activity_id or "").strip()
        if not aid:
            continue
        if urn not in by_urn:
            by_urn[urn] = []
        if aid not in by_urn[urn]:
            by_urn[urn].append(aid)
    return by_urn, n_rows


def _post_id_from_urn(urn: str) -> str:
    return (extract_urn_id(urn) or "").strip()


def _count_author_candidates(
    stems: list[str],
    registry: dict[str, str],
    content_dir: Path,
    limit: int,
) -> int:
    """How many registry entries would be considered for author fetch (before --limit)."""
    n = 0
    for stem in stems:
        urn = (registry.get(stem) or "").strip()
        if not urn:
            continue
        meta_path = content_dir / f"{stem}.meta.json"
        if not meta_path.exists():
            continue
        meta = load_metadata(urn)
        if meta is None:
            continue
        if (str(meta.get("post_author") or "")).strip():
            continue
        post_url = (meta.get("post_url") or "").strip()
        if not post_url or is_comment_feed_url(post_url):
            continue
        n += 1
        if limit and n >= limit:
            break
    return n


def _fetch_author_meta(post_url: str, timeout: float) -> dict[str, str]:
    try:
        resp = requests.get(
            post_url,
            timeout=timeout,
            allow_redirects=True,
            headers=_FETCH_HEADERS,
        )
    except OSError:
        return {}
    if resp.status_code != 200:
        return {}
    if linkedin_http_fetch_is_blocked(resp.url, resp.text):
        return {}
    soup = BeautifulSoup(resp.text, "html.parser")
    return parse_post_meta_from_soup(soup)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--csv",
        type=Path,
        default=None,
        help="activities.csv (default: master CSV under LINKEDIN_DATA_DIR)",
    )
    ap.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Data root (default: get_data_dir())",
    )
    ap.add_argument("--dry-run", action="store_true", help="Print actions only")
    ap.add_argument(
        "--fetch-author",
        action="store_true",
        help="HTTP GET post_url when post_author is still empty after CSV merge",
    )
    ap.add_argument(
        "--sleep",
        type=float,
        default=1.0,
        help="Seconds between author GETs (default 1)",
    )
    ap.add_argument("--timeout", type=float, default=15.0, help="HTTP timeout per GET")
    ap.add_argument("--limit", type=int, default=0, help="Max author GETs (0 = no cap)")
    ap.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Debug logging (per-file CSV merge lines)",
    )
    ap.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Only warnings and errors",
    )
    ap.add_argument(
        "--progress-every",
        type=int,
        default=25,
        metavar="N",
        help="Log CSV merge progress every N metadata files (0 = only start/end)",
    )
    args = ap.parse_args()

    if args.quiet and args.verbose:
        print("Use only one of --quiet or --verbose", file=sys.stderr)
        return 2
    log_level = (
        logging.DEBUG
        if args.verbose
        else (logging.WARNING if args.quiet else logging.INFO)
    )
    logging.basicConfig(
        level=log_level,
        format="%(levelname)s %(message)s",
        stream=sys.stderr,
    )

    data_dir = args.data_dir or get_data_dir()
    csv_path = args.csv or (data_dir / "activities.csv")
    if not csv_path.exists():
        logger.error("CSV not found: %s", csv_path)
        return 1

    content_dir = data_dir / "content"
    if not content_dir.is_dir():
        logger.error("Content dir not found: %s", content_dir)
        return 1

    registry = _load_registry(content_dir)
    if not registry:
        logger.error("No _urn_registry.json under %s", content_dir)
        return 1

    by_urn, n_csv_rows = _aggregate_csv_by_post_urn(csv_path)
    stems = sorted(registry.keys())
    eligible = [
        s
        for s in stems
        if (registry.get(s) or "").strip() and (content_dir / f"{s}.meta.json").exists()
    ]
    logger.info(
        "Starting CSV identity merge: data_dir=%s csv=%s (%d rows) content=%s "
        "(%d registry URNs, %d with .meta.json)",
        data_dir,
        csv_path,
        n_csv_rows,
        content_dir,
        len(registry),
        len(eligible),
    )

    csv_merged = 0
    author_fetches = 0
    author_updated = 0
    total_eligible = len(eligible)
    pe = max(0, args.progress_every)

    for i, stem in enumerate(eligible, 1):
        urn = (registry.get(stem) or "").strip()

        extra_ids = by_urn.get(urn, [])
        pid = _post_id_from_urn(urn)
        if args.dry_run:
            meta = load_metadata(urn)
            if meta is None:
                continue
            need_ids = not (meta.get("activities_ids") or [])
            need_pid = not (str(meta.get("post_id") or "")).strip()
            if extra_ids or need_ids or need_pid:
                logger.info(
                    "[dry-run] would merge CSV identity [%d/%d] urn=%s... extra_ids=%d",
                    i,
                    total_eligible,
                    urn[:56],
                    len(extra_ids),
                )
            continue

        out = merge_post_identity(
            urn,
            post_id=pid,
            post_urn=urn,
            extra_activity_ids=extra_ids,
        )
        if out is not None:
            csv_merged += 1
            logger.debug(
                "merged [%d/%d] urn=%s... +%d activity_id(s)",
                i,
                total_eligible,
                urn[:48],
                len(extra_ids),
            )
        if pe and (i % pe == 0 or i == total_eligible):
            logger.info(
                "CSV merge progress %d/%d (%d file(s) updated so far)",
                i,
                total_eligible,
                csv_merged,
            )

    if not args.dry_run:
        logger.info("CSV identity merge done: updated %d metadata file(s)", csv_merged)
    else:
        logger.info("[dry-run] CSV identity pass finished (no files written)")

    if not args.fetch_author:
        logger.info(
            "Done (no --fetch-author). Re-run with --fetch-author to fill post_author from HTML."
        )
        return 0

    if args.dry_run:
        logger.info(
            "[dry-run] author pass would run after CSV merge (use without --dry-run)."
        )

    # Second pass: optional HTTP for missing author
    author_plan = _count_author_candidates(stems, registry, content_dir, 0)
    to_do = min(author_plan, args.limit) if args.limit else author_plan
    logger.info(
        "Starting author fetch pass: %d candidate(s)%s, sleep=%.2fs timeout=%.1fs",
        author_plan,
        f" (processing up to {args.limit})" if args.limit else "",
        args.sleep,
        args.timeout,
    )

    fetches = 0
    for stem in stems:
        urn = (registry.get(stem) or "").strip()
        if not urn:
            continue
        meta = load_metadata(urn)
        if meta is None:
            continue
        if (str(meta.get("post_author") or "")).strip():
            continue
        post_url = (meta.get("post_url") or "").strip()
        if not post_url or is_comment_feed_url(post_url):
            continue
        if args.limit and fetches >= args.limit:
            break

        if args.dry_run:
            logger.info(
                "[dry-run] would fetch author [%d] %s",
                fetches + 1,
                post_url[:90],
            )
            fetches += 1
            continue

        denom = max(to_do, 1) if to_do else max(author_plan, 1)
        logger.info(
            "Author GET [%d/%d] %s",
            author_fetches + 1,
            denom,
            post_url[:100],
        )
        html_meta = _fetch_author_meta(post_url, args.timeout)
        author_fetches += 1
        fetches += 1
        if not html_meta.get("post_author") and not html_meta.get("post_author_url"):
            logger.info("  -> no post_author / post_author_url (wall or parse miss)")
            if args.sleep > 0:
                time.sleep(args.sleep)
            continue

        kwargs: dict = {}
        if html_meta.get("post_author"):
            kwargs["post_author"] = html_meta["post_author"]
        if html_meta.get("post_author_url"):
            kwargs["post_author_url"] = html_meta["post_author_url"]
        if (
            html_meta.get("post_created_at")
            and not (str(meta.get("post_created_at") or "")).strip()
        ):
            kwargs["post_created_at"] = html_meta["post_created_at"]

        if kwargs:
            update_metadata_fields(urn, **kwargs)
            author_updated += 1
            pa = kwargs.get("post_author", "")
            logger.info(
                "  -> updated author=%s url=%s",
                (str(pa)[:40] + "...") if len(str(pa)) > 40 else pa,
                "yes" if kwargs.get("post_author_url") else "no",
            )
        if args.sleep > 0:
            time.sleep(args.sleep)

    logger.info(
        "Author fetch done: %d GET(s), %d file(s) updated with post_author / post_author_url.",
        author_fetches,
        author_updated,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
