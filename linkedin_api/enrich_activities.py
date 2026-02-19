#!/usr/bin/env python3
"""
Phase 2: Enrich activities with post content.

Reads activities JSON (from summarize_activity). For each activity with post_url
and empty content, fetches the page: tries a simple HTTP request first; falls
back to browser on 403/login wall. Tries CDP connect (browser-use then Playwright)
to existing Chrome (--remote-debugging-port=9222); else Playwright launches
dedicated profile.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from linkedin_api.activity_csv import get_data_dir
from linkedin_api.content_store import (
    load_content,
    load_metadata,
    save_content,
    save_metadata,
)
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


def _fetch_with_requests(url: str) -> tuple[str, list[str]] | None:
    """
    Try simple HTTP request. Returns (content, urls) if successful, None if
    we need browser fallback (403, login wall, or empty content).
    """
    try:
        resp = requests.get(url, timeout=10, allow_redirects=True)
        if resp.status_code != 200:
            return None
        content = _parse_content_from_html(resp.text)
        if not content or len(content) < 50:
            return None
        # Login wall: title often contains "Sign In" or similar
        soup = BeautifulSoup(resp.text, "html.parser")
        title_elem = soup.find("title")
        title = title_elem.get_text(strip=True) if title_elem else ""
        if "sign in" in title.lower() or "login" in title.lower():
            return None
        return content, extract_urls_from_text(content)
    except Exception:
        return None


async def _enrich_one_url(
    url: str, browser, *, wait_s: float = 3.5, debug_save_path: Path | None = None
) -> tuple[str, list[str]]:
    """Visit URL with browser-use BrowserSession. Caller owns lifecycle."""
    html = None
    try:
        page = await browser.new_page(url)
        await asyncio.sleep(wait_s)  # Let LinkedIn JS render post content
        html = await page.evaluate("() => document.documentElement.outerHTML")
    except Exception as e:
        if debug_save_path:
            debug_save_path.write_text(
                f"<!-- Error: {e} -->\n<!-- URL: {url} -->",
                encoding="utf-8",
            )
        raise
    if debug_save_path and html is not None:
        debug_save_path.write_text(str(html), encoding="utf-8", errors="replace")
    if isinstance(html, str):
        content = _parse_content_from_html(html)
        urls = extract_urls_from_text(content)
        return content, urls
    return "", []


async def _enrich_one_url_playwright(
    url: str,
    context,
    *,
    wait_s: float = 3.5,
    debug_save_path: Path | None = None,
) -> tuple[str, list[str]]:
    """Visit URL with Playwright context. Caller owns lifecycle."""
    page = None
    html = None
    try:
        page = await context.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(wait_s)
        html = await page.evaluate("() => document.documentElement.outerHTML")
    except Exception as e:
        if debug_save_path:
            debug_save_path.write_text(
                f"<!-- Error: {e} -->\n<!-- URL: {url} -->",
                encoding="utf-8",
            )
        raise
    finally:
        if page:
            await page.close()
    if debug_save_path and html is not None:
        debug_save_path.write_text(str(html), encoding="utf-8", errors="replace")
    if isinstance(html, str):
        content = _parse_content_from_html(html)
        urls = extract_urls_from_text(content)
        return content, urls
    return "", []


def _get_chrome_profile_kwargs() -> dict:
    """Return browser kwargs for Chrome profile (LinkedIn login)."""
    import os
    import platform

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
    *,
    wait_s: float = 3.5,
    debug_save_path: Path | None = None,
    confirm: bool = True,
) -> int:
    """Try requests first; use store when available; browser-use as last resort."""
    enriched_count = 0
    needs_browser: list[dict] = []

    for rec in to_enrich:
        urn = rec.get("post_urn", "")
        url = rec.get("post_url", "")
        if not urn or not url:
            continue

        # 1) Prefer existing content in the store
        stored = load_content(urn)
        if stored and len(stored) >= 50:
            rec["content"] = stored
            meta = load_metadata(urn)
            rec["urls"] = list(meta.get("urls", [])) if meta else []
            enriched_count += 1
            continue

        # 2) Try simple HTTP fetch
        result = _fetch_with_requests(url)
        if result:
            content, urls = result
            rec["content"] = content
            rec["urls"] = urls
            save_content(urn, content)
            save_metadata(urn, urls=urls, post_url=url)
            enriched_count += 1
        else:
            needs_browser.append(rec)

    if not needs_browser:
        return enriched_count

    urls_to_visit = [
        rec.get("post_url", "") for rec in needs_browser if rec.get("post_url")
    ]
    print("\nURLs to visit with browser:")
    for u in urls_to_visit:
        print(f"  {u}")
    if confirm:
        reply = input("Continue? [Y/n]: ").strip().lower()
        if reply and reply != "y":
            return enriched_count

    cdp_url = os.environ.get("CHROME_DEBUG_PORT", "http://localhost:9222")
    if not cdp_url.startswith("http"):
        cdp_url = f"http://localhost:{cdp_url}"

    # 1) Try browser-use only when Chrome is already in debug mode (cdp_url works).
    #    browser-use launch is fragile (Chrome 136+, CDP init); we use Playwright for launch.
    browser = None
    try:
        from browser_use import BrowserSession

        browser = BrowserSession(cdp_url=cdp_url)
        await asyncio.wait_for(browser.start(), timeout=6.0)
    except (asyncio.TimeoutError, Exception):
        pass

    if browser is not None:
        try:
            for rec in needs_browser:
                urn = rec.get("post_urn", "")
                url = rec.get("post_url", "")
                if not urn or not url:
                    continue
                try:
                    content, urls = await _enrich_one_url(
                        url,
                        browser,
                        wait_s=wait_s,
                        debug_save_path=debug_save_path,
                    )
                    if content:
                        rec["content"] = content
                        rec["urls"] = urls
                        save_content(urn, content)
                        save_metadata(urn, urls=urls, post_url=url)
                        enriched_count += 1
                except Exception as e:
                    rec["_enrich_error"] = str(e)
        finally:
            await browser.kill()
        return enriched_count

    # 2) Fallback: Playwright (CDP connect or launch dedicated profile)
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        owns_context = False
        try:
            browser = await p.chromium.connect_over_cdp(cdp_url, timeout=4000)
            context = (
                browser.contexts[0] if browser.contexts else await browser.new_context()
            )
            print("Connected to existing Chrome (remote debugging).")
        except Exception:
            print(
                "Chrome not in debug mode; launching dedicated profile. "
                "For your profile: start Chrome with --remote-debugging-port=9222"
            )
            profile_dir = get_data_dir() / "browser_profile"
            profile_dir.mkdir(parents=True, exist_ok=True)
            context = await p.chromium.launch_persistent_context(
                str(profile_dir),
                headless=False,
                channel="chrome",
            )
            owns_context = True

        try:
            for rec in needs_browser:
                urn = rec.get("post_urn", "")
                url = rec.get("post_url", "")
                if not urn or not url:
                    continue
                try:
                    content, urls = await _enrich_one_url_playwright(
                        url,
                        context,
                        wait_s=wait_s,
                        debug_save_path=debug_save_path,
                    )
                    if content:
                        rec["content"] = content
                        rec["urls"] = urls
                        save_content(urn, content)
                        save_metadata(urn, urls=urls, post_url=url)
                        enriched_count += 1
                except Exception as e:
                    rec["_enrich_error"] = str(e)
        finally:
            if owns_context:
                await context.close()

    return enriched_count


def enrich_activities(
    activities: list[dict],
    *,
    limit: int | None = None,
    use_browser: bool = True,
    wait_s: float = 3.5,
    debug_save_path: Path | None = None,
    confirm: bool = True,
) -> tuple[list[dict], int]:
    """
    Enrich activities that have post_url but empty content.
    Returns (enriched_activities, count_enriched).
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
    enriched_count = asyncio.run(
        _run_enrichment(
            to_enrich,
            browser_kwargs,
            wait_s=wait_s,
            debug_save_path=debug_save_path,
            confirm=confirm,
        )
    )
    return activities, enriched_count


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Enrich activities with post content (browser-use or Playwright).",
    )
    parser.add_argument(
        "input",
        type=Path,
        nargs="?",
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
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Save last fetched HTML to outputs/debug_enrich_last.html for inspection",
    )
    parser.add_argument(
        "--wait",
        type=float,
        default=3.5,
        metavar="SECONDS",
        help="Seconds to wait for page load (default: 3.5)",
    )
    args = parser.parse_args()
    if not args.input or not args.input.exists():
        parser.error("Input file required")
    activities = json.loads(args.input.read_text())
    if args.no_browser:
        print(f"Loaded {len(activities)} activities (dry run, no enrichment)")
        out_path = args.output or args.input.with_name(
            args.input.stem + "_enriched" + args.input.suffix
        )
        out_path.write_text(json.dumps(activities, indent=2))
        return 0
    debug_path = None
    if args.debug:
        debug_path = OUTPUT_DIR / "debug_enrich_last.html"
        debug_path.parent.mkdir(parents=True, exist_ok=True)
    enriched, count = enrich_activities(
        activities,
        limit=args.limit,
        use_browser=True,
        wait_s=args.wait,
        debug_save_path=debug_path,
    )
    out_path = args.output or args.input.with_name(
        args.input.stem + "_enriched" + args.input.suffix
    )
    out_path.write_text(json.dumps(enriched, indent=2))
    print(f"Enriched {count} activities, wrote {out_path}")
    if args.debug and debug_path:
        print(f"Debug: last page HTML → {debug_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
