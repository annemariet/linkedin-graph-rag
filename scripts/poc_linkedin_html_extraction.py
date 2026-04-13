#!/usr/bin/env python3
"""
POC: compare LinkedIn post HTML extraction strategies on one or more URLs.

Run (``trafilatura`` is a core dependency)::

    uv sync

Run::

    uv run python scripts/poc_linkedin_html_extraction.py
    uv run python scripts/poc_linkedin_html_extraction.py --url 'https://...'

Compares:
- Current ``linkedin_api`` parsers (plain body, markdown body, JSON-LD author meta).
- Trafilatura (markdown + links + images + optional comments + metadata).

Docling is not included: it targets PDF/Office layouts, not social HTML, and pulls a
large dependency tree. If you need it, wire it similarly behind ``try/except ImportError``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

_FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_DEFAULT_URLS = (
    # User example: Giskard post (ugcPost URL)
    (
        "https://www.linkedin.com/posts/"
        "anhthochuong_im-open-sourcing-my-writing-claude-skill-"
        "ugcPost-7449275736990851072-MO5h"
    ),
    # feed/update form (same post may differ in HTML)
    "https://www.linkedin.com/feed/update/urn:li:activity:7449411510893793281",
)


def _urls_in_text(text: str) -> list[str]:
    from linkedin_api.utils.urls import extract_urls_from_text

    return extract_urls_from_text(text or "")


def _urls_in_markdown(text: str) -> list[str]:
    from linkedin_api.utils.urls import (
        extract_urls_from_markdown,
        extract_urls_from_text,
    )

    t = text or ""
    return list(
        dict.fromkeys(extract_urls_from_markdown(t) + extract_urls_from_text(t))
    )


def _linkedin_paths(html: str, final_url: str) -> dict[str, object]:
    from linkedin_api.utils.post_html import (
        linkedin_http_fetch_is_blocked,
        parse_post_body_markdown_from_soup,
        parse_post_body_from_soup,
        parse_post_meta_from_soup,
    )

    soup = BeautifulSoup(html, "html.parser")
    plain = parse_post_body_from_soup(soup)
    md = parse_post_body_markdown_from_soup(soup, base_url=final_url)
    meta = parse_post_meta_from_soup(soup)
    return {
        "blocked": linkedin_http_fetch_is_blocked(final_url, html),
        "plain_len": len(plain or ""),
        "plain_preview": (plain or "")[:600],
        "plain_urls": _urls_in_text(plain),
        "md_len": len(md or ""),
        "md_preview": (md or "")[:600],
        "md_urls": _urls_in_markdown(md),
        "json_ld_meta": meta,
    }


def _trafilatura_paths(html: str, url: str) -> dict[str, object] | str:
    try:
        from trafilatura import extract, extract_metadata
    except ImportError:
        return "install with: uv sync --extra poc"

    meta = extract_metadata(html)
    meta_dict = meta.as_dict() if meta is not None else {}
    for k in ("body", "commentsbody", "raw_text", "text"):
        if k in meta_dict and not isinstance(
            meta_dict[k], (str, type(None), int, float, bool, list, dict)
        ):
            meta_dict[k] = f"<{type(meta_dict[k]).__name__}>"

    def run_tf(**kwargs) -> str | None:
        return extract(
            html,
            url=url,
            output_format="markdown",
            include_links=True,
            include_images=True,
            include_tables=True,
            include_formatting=True,
            **kwargs,
        )

    md_default = run_tf(include_comments=True)
    md_no_comments = run_tf(include_comments=False)

    return {
        "metadata": meta_dict,
        "markdown_len": len(md_default or ""),
        "markdown_preview": (md_default or "")[:600],
        "markdown_urls": _urls_in_text(md_default),
        "markdown_no_comments_len": len(md_no_comments or ""),
        "markdown_no_comments_preview": (md_no_comments or "")[:600],
    }


def _print_section(title: str, data: dict[str, object] | str) -> None:
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)
    if isinstance(data, str):
        print(data)
        return
    for k, v in data.items():
        if k.endswith("_preview") and isinstance(v, str):
            print(f"\n{k}:\n{v!r}\n")
        elif k == "metadata" or k == "json_ld_meta":
            print(f"\n{k}:\n{json.dumps(v, indent=2, default=str)[:2000]}")
        else:
            print(f"{k}: {v}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "urls",
        nargs="*",
        help="LinkedIn URLs to fetch (default: two built-in examples)",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        help="HTTP timeout seconds",
    )
    args = p.parse_args()
    urls = list(args.urls) if args.urls else list(_DEFAULT_URLS)

    for url in urls:
        print("\n" + "#" * 72)
        print(f"URL: {url}")
        print("#" * 72)
        try:
            r = requests.get(
                url, timeout=args.timeout, allow_redirects=True, headers=_FETCH_HEADERS
            )
        except OSError as e:
            print(f"fetch error: {e}")
            continue
        print(f"status={r.status_code} final={r.url[:120]}...")
        html = r.text
        li = _linkedin_paths(html, r.url or url)
        _print_section("linkedin_api (BeautifulSoup)", li)
        tf = _trafilatura_paths(html, r.url or url)
        _print_section("trafilatura", tf)

    print(
        "\n---\n"
        "Next: pick one primary extractor; unify metadata + body from its output, "
        "or merge trafilatura markdown when len > threshold and linkedin_api meta."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
