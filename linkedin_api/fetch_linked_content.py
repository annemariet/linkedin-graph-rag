"""
Fetch content from URLs linked in LinkedIn posts/comments.

Pluggable extractor with strategy dispatch by URL type.

MVP: simple HTML→text via BeautifulSoup body.
Later: trafilatura for articles (Substack, Medium, blogs);
       metadata-only for YouTube/GitHub.

Storage
-------
Fetched resource content is persisted in the *resource store*:
  ``get_data_dir() / "resources/"``
Each URL is identified by the SHA-256 hash of its (resolved) URL.
  - ``{hash}.json``  — FetchResult (including title and body text)
  - ``{hash}.md``    — body text as plain text / future Markdown

Typical pipeline
----------------
1. Post content (from API or HTTP fetch) is stored in the content store.
2. ``enrich_activities`` populates ``meta.json`` ``urls`` field.
3. This module reads those URLs and fetches their content.

CLI
---
  uv run python -m linkedin_api.fetch_linked_content          # all posts
  uv run python -m linkedin_api.fetch_linked_content --limit 5
  uv run python -m linkedin_api.fetch_linked_content --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import requests
from bs4 import BeautifulSoup

from linkedin_api.activity_csv import get_data_dir
from linkedin_api.utils.urls import categorize_url, resolve_redirect, should_ignore_url

# ---------------------------------------------------------------------------
# Request headers
# ---------------------------------------------------------------------------

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# ---------------------------------------------------------------------------
# FetchResult
# ---------------------------------------------------------------------------


@dataclass
class FetchResult:
    """Result of fetching a single linked resource URL."""

    url: str
    resolved_url: str = ""
    title: str = ""
    content: str = ""
    url_type: str = ""
    domain: str = ""
    error: str = ""
    fetched_at: str = ""

    @property
    def ok(self) -> bool:
        """True if at least a title or content was retrieved without error."""
        return bool((self.content or self.title) and not self.error)


# ---------------------------------------------------------------------------
# Strategy type alias
# ---------------------------------------------------------------------------

FetchStrategy = Callable[[str], tuple[str, str]]  # returns (title, content)

# ---------------------------------------------------------------------------
# Concrete strategies
# ---------------------------------------------------------------------------


def _fetch_html_body(url: str) -> tuple[str, str]:
    """MVP: extract title and body text using BeautifulSoup.

    Removes <script>, <style>, <nav>, <header>, <footer>, and <aside>
    elements before extracting text, to reduce noise.
    """
    resp = requests.get(url, timeout=15, allow_redirects=True, headers=_HEADERS)
    if resp.status_code != 200:
        raise ValueError(f"HTTP {resp.status_code}")

    soup = BeautifulSoup(resp.text, "html.parser")

    # Prefer og:title over <title> (cleaner for articles)
    title = ""
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        title = str(og_title["content"]).strip()
    elif soup.title:
        title = soup.title.get_text(strip=True)

    # Remove chrome/noise elements
    for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()

    body = soup.find("body") or soup
    lines = [
        ln.strip() for ln in body.get_text(separator="\n").splitlines() if ln.strip()
    ]
    content = "\n".join(lines)
    return title, content


def _fetch_metadata_only(url: str) -> tuple[str, str]:
    """Metadata-only fetch: title via og: tags, no body extraction.

    Used for video platforms (YouTube), code repositories (GitHub), etc.
    Full content extraction for these types is deferred to a later phase.
    """
    resp = requests.get(url, timeout=10, allow_redirects=True, headers=_HEADERS)
    if resp.status_code != 200:
        raise ValueError(f"HTTP {resp.status_code}")

    soup = BeautifulSoup(resp.text, "html.parser")
    title = ""
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        title = str(og_title["content"]).strip()
    elif soup.title:
        title = soup.title.get_text(strip=True)

    # Return empty content — body extraction is not implemented for this type
    return title, ""


# ---------------------------------------------------------------------------
# Strategy registry  (dispatch table — extend here for new URL types)
# ---------------------------------------------------------------------------

#: Maps url_type → fetch strategy.  Add entries here to support new types.
STRATEGIES: dict[str, FetchStrategy] = {
    "article": _fetch_html_body,
    "documentation": _fetch_html_body,
    "research": _fetch_html_body,
    "tool": _fetch_html_body,
    "social": _fetch_html_body,
    "product": _fetch_html_body,
    # Metadata-only (body extraction deferred)
    "video": _fetch_metadata_only,
    "repository": _fetch_metadata_only,
    "podcast": _fetch_metadata_only,
}

#: URL types whose content we never attempt to fetch (binary / media files).
SKIP_TYPES: frozenset[str] = frozenset(
    {"image", "document", "presentation", "archive", "audio"}
)

# ---------------------------------------------------------------------------
# Resource store (keyed by SHA-256 of the resolved URL)
# ---------------------------------------------------------------------------


def _resource_dir() -> Path:
    """Return (and create) the resource storage directory."""
    d = get_data_dir() / "resources"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _url_stem(url: str) -> str:
    """Stable filename stem derived from the URL."""
    return hashlib.sha256(url.encode()).hexdigest()


def has_resource(url: str) -> bool:
    """True if a FetchResult has been stored for *url*."""
    return (_resource_dir() / f"{_url_stem(url)}.json").exists()


def save_resource(url: str, result: FetchResult) -> Path:
    """Persist *result* for *url*.

    Writes two files:
    - ``{stem}.json``  — full FetchResult dict
    - ``{stem}.md``    — body text (empty string if none)
    """
    stem = _url_stem(url)
    resource_dir = _resource_dir()

    json_path = resource_dir / f"{stem}.json"
    json_path.write_text(
        json.dumps(asdict(result), indent=0, ensure_ascii=False), encoding="utf-8"
    )

    md_path = resource_dir / f"{stem}.md"
    md_path.write_text(result.content or "", encoding="utf-8")

    return json_path


def load_resource(url: str) -> FetchResult | None:
    """Load a stored FetchResult for *url*, or ``None`` if not found."""
    json_path = _resource_dir() / f"{_url_stem(url)}.json"
    if not json_path.exists():
        return None
    data: dict = json.loads(json_path.read_text(encoding="utf-8"))
    return FetchResult(**data)


# ---------------------------------------------------------------------------
# Core fetch logic
# ---------------------------------------------------------------------------


def fetch_linked_content(
    url: str,
    *,
    resolve_redirects: bool = True,
) -> FetchResult:
    """Fetch content from a linked URL using the appropriate strategy.

    1. Skips ignored URLs (LinkedIn profiles, hashtags, etc.).
    2. Resolves redirects (including ``lnkd.in`` short URLs).
    3. Dispatches to the registered strategy for the detected URL type.
    4. Falls back to ``_fetch_html_body`` for unknown types.

    Returns a :class:`FetchResult`; never raises.
    """
    if should_ignore_url(url):
        return FetchResult(url=url, error="ignored")

    resolved = resolve_redirect(url) if resolve_redirects else url
    info = categorize_url(resolved)
    url_type = info.get("type") or "article"
    domain = info.get("domain") or ""

    if url_type in SKIP_TYPES:
        return FetchResult(
            url=url,
            resolved_url=resolved,
            url_type=url_type,
            domain=domain,
            error=f"skipped ({url_type})",
        )

    strategy = STRATEGIES.get(url_type, _fetch_html_body)
    try:
        title, content = strategy(resolved)
        return FetchResult(
            url=url,
            resolved_url=resolved,
            title=title,
            content=content,
            url_type=url_type,
            domain=domain,
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as exc:
        return FetchResult(
            url=url,
            resolved_url=resolved,
            url_type=url_type,
            domain=domain,
            error=str(exc),
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )


def process_post_linked_content(
    urls: list[str],
    *,
    skip_cached: bool = True,
) -> list[FetchResult]:
    """Fetch and store content for a list of URLs extracted from a post.

    Args:
        urls: URLs to process (typically from post metadata).
        skip_cached: If True, skip URLs already in the resource store.

    Returns:
        List of :class:`FetchResult` (including failures and skips).
    """
    results: list[FetchResult] = []
    for url in urls:
        if skip_cached and has_resource(url):
            cached = load_resource(url)
            if cached is not None:
                results.append(cached)
                continue
        result = fetch_linked_content(url)
        if result.ok:
            save_resource(url, result)
        results.append(result)
    return results


# ---------------------------------------------------------------------------
# Pipeline integration (streaming)
# ---------------------------------------------------------------------------


def fetch_linked_content_streaming(
    limit: int | None = None,
    skip_cached: bool = True,
):
    """
    Generator for pipeline use. Yields (posts_done, total_posts) after each post.

    Returns total URLs fetched via StopIteration.value.
    """
    posts = list(_iter_posts_with_urls())
    if limit:
        posts = posts[:limit]
    urls_fetched = 0
    for i, (urn, urls) in enumerate(posts):
        results = process_post_linked_content(urls, skip_cached=skip_cached)
        urls_fetched += sum(1 for r in results if r.ok)
        yield i + 1, len(posts)
    return urls_fetched


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _iter_posts_with_urls():
    """Yield (urn, urls) for all posts that have URLs in their metadata."""
    from linkedin_api.content_store import _content_dir, _load_registry

    content_dir = _content_dir()
    registry = _load_registry()

    for meta_path in sorted(content_dir.glob("*.meta.json")):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        urls = meta.get("urls") or []
        if not urls:
            continue
        stem = meta_path.stem.removesuffix(".meta").removesuffix("")
        # stem is the hash part before ".meta"
        stem = meta_path.name.replace(".meta.json", "")
        urn = registry.get(stem, "")
        yield urn, urls


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch content from URLs linked in LinkedIn posts/comments.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max number of posts to process (for testing).",
    )
    parser.add_argument(
        "--skip-cached",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Skip URLs already in the resource store (default: on).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be fetched without actually fetching.",
    )
    args = parser.parse_args()

    posts_processed = 0
    urls_fetched = 0
    urls_failed = 0
    urls_skipped = 0

    for urn, urls in _iter_posts_with_urls():
        if args.limit and posts_processed >= args.limit:
            break

        label = urn or "(unknown URN)"
        print(f"\n📄 {label}  ({len(urls)} URL(s))")

        if args.dry_run:
            for url in urls:
                cached = " [cached]" if has_resource(url) else ""
                print(f"   {url}{cached}")
            posts_processed += 1
            continue

        results = process_post_linked_content(urls, skip_cached=args.skip_cached)
        for res in results:
            if res.error == "ignored" or res.error.startswith("skipped"):
                urls_skipped += 1
                print(f"   ⏭  {res.url}  ({res.error})")
            elif res.ok:
                urls_fetched += 1
                print(
                    f"   ✅ {res.resolved_url or res.url}  [{res.url_type}] {res.title!r}"
                )
            else:
                urls_failed += 1
                print(f"   ❌ {res.url}  {res.error}")

        posts_processed += 1

    print(
        f"\n✨ Done — {posts_processed} post(s) processed, "
        f"{urls_fetched} URL(s) fetched, "
        f"{urls_skipped} skipped, "
        f"{urls_failed} failed."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
