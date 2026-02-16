#!/usr/bin/env python3
"""
Phase 2: Enrich activities with post content via browser-use.

Reads activities JSON (from summarize_activity). For each activity with post_url
and empty content, visits the LinkedIn URL using browser-use (with Chrome profile
for login) and extracts post body text. Populates content and urls for downstream
summarization and linked-resource pipelines.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from bs4 import BeautifulSoup

from linkedin_api.extract_resources import extract_urls_from_text

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs"

_CONTENT_SELECTORS = [
    "article[data-id]",
    ".feed-shared-update-v2__description",
    ".feed-shared-text",
    '[data-test-id="main-feed-activity-card"]',
]


def _parse_content_from_html(html: str) -> str:
    """Extract post body text from LinkedIn page HTML."""
    soup = BeautifulSoup(html, "html.parser")
    content_text = []
    for selector in _CONTENT_SELECTORS:
        for elem in soup.select(selector):
            text = elem.get_text(strip=True)
            if text and len(text) > 20:
                content_text.append(text)
    if content_text:
        return "\n".join(content_text)
    og = soup.find("meta", property="og:description")
    if og and og.get("content"):
        content_text.append(og["content"])
    title = soup.find("title")
    if title:
        t = title.get_text(strip=True)
        if " | " in t:
            content_text.append(t.split(" | ")[0])
    return "\n".join(content_text) if content_text else ""


def _is_comment_feed_url(url: str) -> bool:
    """True if URL targets a comment (not a post); skip for content extraction."""
    return bool(url and "urn:li:comment:" in url)


async def _enrich_one_url(url: str, browser) -> tuple[str, list[str]]:
    """Visit URL, extract content and URLs. Caller owns browser lifecycle."""
    from browser_use.actor import Page
    from browser_use.browser.events import NavigateToUrlEvent

    await browser.event_bus.dispatch_and_await(
        NavigateToUrlEvent(url=url, new_tab=False)
    )
    await asyncio.sleep(1.5)  # Let LinkedIn content load
    page = Page(
        browser_session=browser,
        target_id=browser.get_current_tab_id(),
    )
    html = await page.evaluate("() => document.documentElement.outerHTML")
    if isinstance(html, str):
        content = _parse_content_from_html(html)
        urls = extract_urls_from_text(content)
        return content, urls
    return "", []


def _get_chrome_profile_kwargs() -> dict:
    """Return browser kwargs for Chrome profile (LinkedIn login)."""
    import platform
    import os

    system = platform.system()
    if system == "Darwin":
        data_dir = os.path.expanduser("~/Library/Application Support/Google/Chrome")
        executable = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    elif system == "Linux":
        data_dir = os.path.expanduser("~/.config/google-chrome")
        executable = "/usr/bin/google-chrome"
    else:
        return {}
    if Path(data_dir).exists() and Path(executable).exists():
        return {
            "executable_path": executable,
            "user_data_dir": data_dir,
            "profile_directory": "Default",
        }
    return {}


async def _run_enrichment(
    to_enrich: list[dict],
    browser_kwargs: dict,
) -> int:
    """Run enrichment for all items in one browser session."""
    from browser_use import BrowserSession

    browser = BrowserSession(**browser_kwargs)
    await browser.start()
    enriched_count = 0
    try:
        for rec in to_enrich:
            url = rec.get("post_url", "")
            try:
                content, urls = await _enrich_one_url(url, browser)
                if content:
                    rec["content"] = content
                    rec["urls"] = urls
                    enriched_count += 1
            except Exception as e:
                rec["_enrich_error"] = str(e)
    finally:
        await browser.kill()
    return enriched_count


def enrich_activities(
    activities: list[dict],
    *,
    limit: int | None = None,
    use_browser: bool = True,
) -> tuple[list[dict], int]:
    """
    Enrich activities that have post_url but empty content.
    Returns (enriched_activities, count_enriched).
    Requires Chrome closed when using profile (LinkedIn login).
    """
    to_enrich = [
        a
        for a in activities
        if a.get("post_url")
        and not a.get("content")
        and not _is_comment_feed_url(a.get("post_url", ""))
    ]
    if limit:
        to_enrich = to_enrich[:limit]
    if not to_enrich:
        return activities, 0

    browser_kwargs = _get_chrome_profile_kwargs() if use_browser else {}
    enriched_count = asyncio.run(_run_enrichment(to_enrich, browser_kwargs))
    return activities, enriched_count


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Enrich activities with post content via browser-use."
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Activities JSON file (from summarize_activity -o)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output path (default: input with _enriched suffix)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Max number of posts to enrich (for testing)",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Skip enrichment (dry run)",
    )
    args = parser.parse_args()
    if not args.input.exists():
        print(f"Input file not found: {args.input}")
        return 1
    activities = json.loads(args.input.read_text())
    if args.no_browser:
        print(f"Loaded {len(activities)} activities (dry run, no enrichment)")
        out_path = args.output or args.input.with_name(
            args.input.stem + "_enriched" + args.input.suffix
        )
        out_path.write_text(json.dumps(activities, indent=2))
        return 0
    enriched, count = enrich_activities(activities, limit=args.limit, use_browser=True)
    out_path = args.output or args.input.with_name(
        args.input.stem + "_enriched" + args.input.suffix
    )
    out_path.write_text(json.dumps(enriched, indent=2))
    print(f"Enriched {count} activities, wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
