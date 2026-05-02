#!/usr/bin/env python3
"""
Scan the resource store and remove files that contain LinkedIn auth/internal
page content instead of actual external resource content.

Dry-run by default — pass --delete to actually remove files.

Usage:
    uv run python scripts/cleanup_noisy_resources.py
    uv run python scripts/cleanup_noisy_resources.py --delete
    uv run python scripts/cleanup_noisy_resources.py --delete --verbose
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


def _strip_utm(url: str) -> str:
    """Strip utm_* params — mirrors fetch_linked_content.strip_utm_params."""
    if not url:
        return url
    try:
        parsed = urlparse(url)
        query = urlencode(
            [
                (k, v)
                for k, v in parse_qsl(parsed.query)
                if not k.lower().startswith("utm_")
            ]
        )
        return urlunparse(parsed._replace(query=query))
    except Exception:
        return url


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

# LinkedIn internal URL path fragments that are never real external resources.
_LI_INTERNAL_PATHS = [
    "linkedin.com/signup/",
    "linkedin.com/authwall",
    "linkedin.com/uas/login",
    "linkedin.com/cookie-policy",
    "linkedin.com/legal/cookie",
    "linkedin.com/feed/hashtag/",
    "linkedin.com/company/",
    "linkedin.com/showcase/",
    "linkedin.com/in/",
    "linkedin.com/pub/",
    "linkedin.com/school/",
    "linkedin.com/redir/redirect",
    "linkedin.com/redir/externalredirect",
]

# Titles that indicate a LinkedIn auth page, not a real resource page.
# NOTE: content-based detection was removed — LinkedIn injects its cookie-consent
# banner ("agree & join linkedin", "linkedin respects your privacy") into ALL
# LinkedIn pages including legitimate Pulse articles, causing false positives.
# URL + title detection is precise enough.
_LI_BAD_TITLES = [
    "sign up | linkedin",
    "before you continue to linkedin",
    "linkedin: log in or sign up",
    "log in or sign up | linkedin",
    "external redirection | linkedin",
]


def _is_linkedin_feed_url(url: str) -> bool:
    u = url.lower()
    # www.linkedin.com/feed/update/... etc. — but NOT /feed/hashtag/ (already in _LI_INTERNAL_PATHS)
    return u.startswith("https://www.linkedin.com/feed/") or u.startswith(
        "http://www.linkedin.com/feed/"
    )


def _is_utm_orphan(stem: str, data: dict) -> bool:
    """True if this file was keyed by a UTM-containing URL.

    After the canonical-key change, resource files are stored under
    hash(strip_utm(url)).  Files that were stored under the old
    hash(url_with_utm) key will never be found by the pipeline again
    and should be deleted so the next run re-fetches them under the
    correct canonical key.
    """
    url = (data.get("url") or "").strip()
    if not url:
        return False
    canonical = _strip_utm(url)
    if canonical == url:
        return False  # no UTM params — not orphaned
    old_stem = hashlib.sha256(url.encode()).hexdigest()
    return stem == old_stem


def classify(data: dict, stem: str = "") -> tuple[bool, str]:
    """Return (is_noisy, reason). Uses resolved_url when available."""
    url = (data.get("resolved_url") or data.get("url") or "").strip()
    url_lower = url.lower()

    for fragment in _LI_INTERNAL_PATHS:
        if fragment in url_lower:
            return True, f"LinkedIn internal URL: {fragment}"

    if _is_linkedin_feed_url(url):
        return True, "LinkedIn feed URL"

    title_lower = (data.get("title") or "").lower()
    for bad in _LI_BAD_TITLES:
        if bad in title_lower:
            return True, f"LinkedIn auth title: {data.get('title')!r}"

    if stem and _is_utm_orphan(stem, data):
        canonical = _strip_utm(data.get("url") or "")
        return True, f"UTM-orphaned key (canonical: {canonical})"

    return False, ""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _fix_metadata_urls(content_dir: Path, *, dry_run: bool, verbose: bool) -> int:
    """Canonical-dedup urls field in all meta.json files (no HTTP requests).

    Returns the number of files modified.
    """
    meta_files = sorted(content_dir.glob("*.meta.json"))
    modified = 0
    for path in meta_files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            print(f"  SKIP (unreadable): {path.name} — {e}")
            continue

        urls = data.get("urls")
        if not isinstance(urls, list):
            continue

        seen: set[str] = set()
        deduped: list[str] = []
        for u in urls:
            c = _strip_utm(u)
            if c not in seen:
                seen.add(c)
                deduped.append(u)

        if deduped == urls:
            if verbose:
                print(f"  ok     {path.name}")
            continue

        removed = len(urls) - len(deduped)
        print(f"  FIX    {path.name}  ({removed} duplicate(s) removed)")
        if verbose:
            dupes = [u for u in urls if urls.count(u) > 1]
            for d in dict.fromkeys(dupes):
                print(f"         dup: {d}")

        if not dry_run:
            data["urls"] = deduped
            path.write_text(
                json.dumps(data, indent=0, ensure_ascii=False), encoding="utf-8"
            )
        modified += 1

    return modified


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Actually delete noisy files (default: dry-run only).",
    )
    parser.add_argument(
        "--fix-metadata-urls",
        action="store_true",
        help="Canonical-dedup urls field in all meta.json files (no HTTP). Dry-run unless --delete.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print every file inspected, not just noisy ones.",
    )
    args = parser.parse_args()

    data_dir = Path.home() / ".linkedin_api" / "data"

    if args.fix_metadata_urls:
        content_dir = data_dir / "content"
        if not content_dir.exists():
            print(f"Content directory not found: {content_dir}", file=sys.stderr)
            return 1
        dry_run = not args.delete
        modified = _fix_metadata_urls(
            content_dir, dry_run=dry_run, verbose=args.verbose
        )
        print()
        if dry_run:
            print(f"Found {modified} meta.json file(s) with duplicate URLs.")
            if modified:
                print("Dry-run — pass --delete to apply fixes.")
        else:
            print(f"Fixed {modified} meta.json file(s).")
        return 0

    resources_dir = data_dir / "resources"
    if not resources_dir.exists():
        print(f"Resources directory not found: {resources_dir}", file=sys.stderr)
        return 1

    json_files = sorted(resources_dir.glob("*.json"))
    total = len(json_files)
    noisy: list[tuple[Path, str]] = []
    reasons: Counter = Counter()

    for json_path in json_files:
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            print(f"  SKIP (unreadable): {json_path.name} — {e}")
            continue

        is_noisy, reason = classify(data, stem=json_path.stem)
        if is_noisy:
            noisy.append((json_path, reason))
            reasons[reason.split(":")[0].strip()] += 1
            if args.verbose or not args.delete:
                url = data.get("url", "")
                print(f"  NOISY  {json_path.name}  [{reason}]")
                if args.verbose:
                    print(f"         url: {url}")
        else:
            if args.verbose:
                print(f"  ok     {json_path.name}")

    print()
    print(f"Scanned {total} resource files.")
    print(
        f"Found {len(noisy)} noisy files ({len(noisy) * 2} files including .md sidecars)."
    )

    if not noisy:
        print("Nothing to remove.")
        return 0

    print()
    print("Breakdown by reason:")
    for reason, count in reasons.most_common():
        print(f"  {count:4d}  {reason}")

    if not args.delete:
        print()
        print("Dry-run — pass --delete to remove these files.")
        return 0

    print()
    deleted_json = 0
    deleted_md = 0
    for json_path, reason in noisy:
        try:
            json_path.unlink()
            deleted_json += 1
        except OSError as e:
            print(f"  ERROR deleting {json_path.name}: {e}", file=sys.stderr)
        md_path = json_path.with_suffix(".md")
        if md_path.exists():
            try:
                md_path.unlink()
                deleted_md += 1
            except OSError as e:
                print(f"  ERROR deleting {md_path.name}: {e}", file=sys.stderr)

    print(f"Deleted {deleted_json} .json and {deleted_md} .md files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
