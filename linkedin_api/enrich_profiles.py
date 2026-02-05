#!/usr/bin/env python3
"""
Enrich Post nodes with author profile information by scraping LinkedIn URLs.

Extracts author name and profile URL from post HTML and stores them as properties
on the Post nodes in Neo4j. Can fetch once per URL and parse author + post content
from the same HTML; optionally cache raw HTML for reuse.
"""

import hashlib
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from neo4j import GraphDatabase
from linkedin_api.utils.urns import comment_urn_to_post_url

load_dotenv()

# Dir for caching fetched HTML (optional): outputs/review/cache/
_CACHE_DIR: Optional[Path] = None


def _post_html_cache_dir() -> Optional[Path]:
    global _CACHE_DIR
    if _CACHE_DIR is None:
        base = Path(__file__).resolve().parent.parent
        d = base / "outputs" / "review" / "cache"
        try:
            d.mkdir(parents=True, exist_ok=True)
            _CACHE_DIR = d
        except OSError:
            _CACHE_DIR = False
    return _CACHE_DIR if _CACHE_DIR else None


def _url_to_cache_key(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:32]


def _create_preview_html(html_path: Path) -> Optional[Path]:
    """Extract post content from HTML and create a simple preview HTML for screenshot."""
    try:
        from bs4 import BeautifulSoup

        raw = html_path.read_text(encoding="utf-8", errors="replace")
        soup = BeautifulSoup(raw, "html.parser")

        # Extract post content (same logic as _parse_content_from_soup)
        content_text = []
        og = soup.find("meta", property="og:description")
        og_content = og.get("content") if og and og.get("content") else None
        if og_content:
            content_text.append(og_content)
        
        title = soup.find("title")
        if title:
            t = title.get_text(strip=True)
            if " | " in t:
                title_content = t.split(" | ")[0]
                # Only add title if it's different from og:description to avoid duplicates
                if title_content != og_content:
                    content_text.append(title_content)

        # Extract author info
        author = _parse_author_from_soup(soup)
        author_name = author.get("name") if author else "Unknown"

        # Create simple preview HTML
        preview_content = "\n".join(content_text) if content_text else "No content available"
        preview_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>LinkedIn Post Preview</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
            background: #f3f2ef;
            color: #000000;
        }}
        .post-container {{
            background: #ffffff;
            border-radius: 8px;
            padding: 16px;
            box-shadow: 0 1px 2px rgba(0,0,0,0.1);
        }}
        .author {{
            font-weight: 600;
            font-size: 14px;
            color: #0a66c2;
            margin-bottom: 12px;
            padding-top: 8px;
        }}
        .content {{
            font-size: 14px;
            line-height: 1.5;
            color: #000000;
            white-space: pre-wrap;
            word-wrap: break-word;
            margin-top: 0;
        }}
    </style>
</head>
<body>
    <div class="post-container">
        <div class="author">{author_name}</div>
        <div class="content">{preview_content}</div>
    </div>
</body>
</html>"""

        # Save preview HTML to temp file
        preview_path = html_path.parent / f"{html_path.stem}_preview.html"
        preview_path.write_text(preview_html, encoding="utf-8")
        return preview_path
    except Exception as e:
        logger.warning("Failed to create preview HTML: %s", e)
        return None


def _ensure_thumbnail(html_path: Path, png_path: Path) -> Optional[Path]:
    """Render cached HTML with Playwright and save a screenshot; return png_path if successful."""
    if not html_path.exists() or png_path.exists():
        return png_path if png_path.exists() else None
    t0 = time.perf_counter()
    html_size_kb = html_path.stat().st_size / 1024
    logger.info(
        "Starting thumbnail generation (HTML: %s, size: %.1f KB)",
        html_path.name,
        html_size_kb,
    )
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    except ImportError:
        logger.warning("Playwright not installed; cannot generate thumbnail")
        return None
    
    # Create preview HTML from post content instead of screenshotting full LinkedIn page
    preview_path = _create_preview_html(html_path)
    if not preview_path:
        logger.warning("Could not create preview HTML, falling back to full page screenshot")
        preview_path = html_path
    
    try:
        t1 = time.perf_counter()
        with sync_playwright() as p:
            t2 = time.perf_counter()
            logger.info("Playwright context created (%.1fms)", (t2 - t1) * 1000)
            browser = p.chromium.launch(headless=True)
            t3 = time.perf_counter()
            logger.info("Browser launched (%.1fms)", (t3 - t2) * 1000)
            try:
                # Simple viewport for preview HTML (no need to block network - preview is self-contained)
                context = browser.new_context(viewport={"width": 640, "height": 800})
                page = context.new_page()
                t4 = time.perf_counter()
                logger.info("Page created (%.1fms)", (t4 - t3) * 1000)
                try:
                    page.goto(
                        f"file://{preview_path.resolve()}",
                        wait_until="domcontentloaded",
                        timeout=5000,
                    )
                except PlaywrightTimeout:
                    logger.warning("Page.goto timeout, attempting screenshot anyway")
                t5 = time.perf_counter()
                logger.info("Page navigation done (%.1fms)", (t5 - t4) * 1000)
                page.wait_for_timeout(500)  # Let layout settle
                
                # Screenshot the preview (much simpler - no privacy notice, just post content)
                try:
                    # Focus on the post container
                    post_container = page.locator(".post-container")
                    if post_container.count() > 0:
                        post_container.first.screenshot(path=str(png_path), timeout=5000)
                    else:
                        page.screenshot(path=str(png_path), full_page=False, timeout=5000)
                except PlaywrightTimeout:
                    logger.warning(
                        "Screenshot timed out (10s); LinkedIn page may be too heavy. "
                        "Skipping thumbnail for this item."
                    )
                    return None
                t6 = time.perf_counter()
                logger.info(
                    "Screenshot saved (%.1fms, total: %.1fms)",
                    (t6 - t5) * 1000,
                    (t6 - t0) * 1000,
                )
                return png_path
            finally:
                browser.close()
    except Exception as e:
        elapsed = (time.perf_counter() - t0) * 1000
        logger.exception("Thumbnail generation failed after %.1fms", elapsed)
        return None


# Shared selectors for post content (same as index_content / extract_resources)
_CONTENT_SELECTORS = [
    "article[data-id]",
    ".feed-shared-update-v2__description",
    ".feed-shared-text",
    '[data-test-id="main-feed-activity-card"]',
]

NEO4J_URI = os.getenv("NEO4J_URI") or "neo4j://localhost:7687"
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME") or "neo4j"
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD") or "password"
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE") or "neo4j"


def _normalize_post_url(url: str) -> Optional[str]:
    """Normalize post URLs before fetching HTML."""
    if not url:
        return None

    if "urn:li:comment:" in url:
        comment_url = comment_urn_to_post_url(
            url.replace("https://www.linkedin.com/feed/update/", "")
        )
        if comment_url:
            return comment_url

    return url


def _is_private_post_url(url: str) -> bool:
    """Skip URLs that are not publicly accessible (e.g. group posts).
    activity: and share:/ugcPost: are normal feed posts."""
    return "urn:li:groupPost:" in url


def _parse_author_from_soup(soup: BeautifulSoup) -> Optional[Dict[str, str]]:
    """Extract author name and profile_url from parsed post HTML."""
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if "/in/" not in href or (
            "feed-actor-name" not in href and "actor-name" not in href
        ):
            continue
        profile_url = link["href"].split("?")[0]
        profile_url = re.sub(
            r"https?://[a-z]{2}\.linkedin\.com",
            "https://www.linkedin.com",
            profile_url,
        )
        if (
            not profile_url.startswith("https://www.linkedin.com")
            and "//linkedin.com" in profile_url
        ):
            profile_url = profile_url.replace("//linkedin.com", "//www.linkedin.com")
        name = (
            link.get_text(strip=True)
            if link.string is None
            else (link.string or "").strip()
        )
        if name and 1 < len(name) < 100:
            return {"name": name, "profile_url": profile_url}
    return None


def _parse_content_from_soup(soup: BeautifulSoup) -> str:
    """Extract post body text from parsed HTML (same logic as index_content / extract_resources)."""
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


def fetch_post_page(
    url: str,
    *,
    use_cache: bool = True,
    save_to_cache: bool = True,
) -> Dict[str, Any]:
    """
    Fetch a LinkedIn post URL once; parse author and content from the same HTML.
    Optionally read/write raw HTML under outputs/review/cache/ to avoid repeated requests.

    Returns:
        dict with: url_tried, normalized_url, status_code, html (raw), content (parsed text),
        author (dict or None), error, skip_reason. If from cache, status_code may be None.
    """
    out = {
        "url_tried": url or "",
        "normalized_url": None,
        "status_code": None,
        "html": None,
        "content": "",
        "author": None,
        "error": None,
        "skip_reason": None,
        "from_cache": False,
    }
    if not url:
        out["error"] = "No URL provided."
        return out
    normalized = _normalize_post_url(url)
    out["normalized_url"] = normalized
    if not normalized:
        out["error"] = (
            "Could not normalize URL (e.g. comment URN could not be resolved to post URL)."
        )
        return out
    if _is_private_post_url(normalized):
        out["skip_reason"] = "Private or group post URL; not fetched."
        return out

    cache_dir = _post_html_cache_dir() if (use_cache or save_to_cache) else None
    cache_key = _url_to_cache_key(normalized)
    cached_path = (cache_dir / f"{cache_key}.html") if cache_dir else None

    if use_cache and cached_path and cached_path.exists():
        try:
            raw = cached_path.read_text(encoding="utf-8", errors="replace")
            out["html"] = raw
            out["from_cache"] = True
            soup = BeautifulSoup(raw, "html.parser")
            out["author"] = _parse_author_from_soup(soup)
            out["content"] = _parse_content_from_soup(soup)
            return out
        except Exception as e:
            out["error"] = f"Cache read failed: {e}"
            out["html"] = None

    try:
        response = requests.get(normalized, timeout=10, allow_redirects=True)
        out["status_code"] = response.status_code
        if response.status_code == 404:
            out["error"] = "Not found (404)."
            return out
        response.raise_for_status()
        raw = response.text
        out["html"] = raw
        if save_to_cache and cached_path:
            try:
                cached_path.write_text(raw, encoding="utf-8")
            except OSError:
                pass
        soup = BeautifulSoup(raw, "html.parser")
        out["author"] = _parse_author_from_soup(soup)
        out["content"] = _parse_content_from_soup(soup)
        return out
    except requests.exceptions.HTTPError as e:
        out["error"] = f"HTTP error: {e}"
        return out
    except Exception as e:
        out["error"] = str(e)
        return out


def extract_author_profile(url: str) -> Optional[Dict[str, str]]:
    """
    Extract author profile information from a LinkedIn post URL.

    Looks for profile links with actor-related tracking parameters which
    indicate the post author.

    Args:
        url: LinkedIn post URL

    Returns:
        Dict with 'name' and 'profile_url' or None if extraction failed
    """
    normalized_url = _normalize_post_url(url)
    if not normalized_url:
        return None

    if _is_private_post_url(normalized_url):
        return None

    try:
        response = requests.get(normalized_url, timeout=10, allow_redirects=True)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # Find profile links (format: /in/vanity-name)
        profile_links = soup.find_all("a", href=True)

        for link in profile_links:
            href = link["href"]
            # Look for profile links with actor-name tracking (indicates author)
            # Skip image links (actor-image) as they don't contain text
            if "/in/" in href and ("feed-actor-name" in href or "actor-name" in href):
                # Clean the URL (remove query params)
                profile_url = href.split("?")[0]
                # Normalize country-specific domains (be.linkedin.com -> www.linkedin.com)
                import re

                profile_url = re.sub(
                    r"https?://[a-z]{2}\.linkedin\.com",
                    "https://www.linkedin.com",
                    profile_url,
                )
                # Ensure it starts with https://www.linkedin.com
                if not profile_url.startswith("https://www.linkedin.com"):
                    if "//linkedin.com" in profile_url:
                        profile_url = profile_url.replace(
                            "//linkedin.com", "//www.linkedin.com"
                        )

                # Extract name directly - actor-name links contain only the clean name
                name = (
                    link.get_text(strip=True)
                    if link.string is None
                    else link.string.strip()
                )

                # Valid name found
                if name and len(name) > 1 and len(name) < 100:
                    return {"name": name, "profile_url": profile_url}

        return None

    except Exception as e:
        print(f"   ⚠️  Error extracting author from {url}: {str(e)}")
        return None


def get_thumbnail_path_for_url(url: str) -> Optional[str]:
    """
    Return path to a PNG thumbnail of the post page, or None.
    Requires HTML to be already cached (e.g. after fetch_post_page or extract_author_profile_with_details).
    Uses Playwright to screenshot the cached HTML file; if playwright is not installed, returns None.
    
    Set DISABLE_THUMBNAILS=1 to skip thumbnail generation (useful if Playwright is slow).
    """
    if os.getenv("DISABLE_THUMBNAILS", "").lower() in ("1", "true", "yes"):
        return None
    if not url:
        return None
    normalized = _normalize_post_url(url)
    if not normalized or _is_private_post_url(normalized):
        return None
    cache_dir = _post_html_cache_dir()
    if not cache_dir:
        return None
    cache_key = _url_to_cache_key(normalized)
    html_path = cache_dir / f"{cache_key}.html"
    png_path = cache_dir / f"{cache_key}.png"
    result = _ensure_thumbnail(html_path, png_path)
    return str(result) if result else None


def fetch_post_page_for_ui(
    url: str, *, use_cache: bool = True, save_to_cache: bool = True
) -> Dict[str, Any]:
    """
    Fetch once and return author + content for UI. Same as fetch_post_page;
    name clarifies use. Result includes content (parsed post text) and author.
    """
    return fetch_post_page(url, use_cache=use_cache, save_to_cache=save_to_cache)


def extract_author_profile_with_details(url: str) -> Dict:
    """
    Extract author with details for UI (and parsed content from same fetch).
    Uses single fetch; returns url_tried, normalized_url, status_code, author,
    content (post text), error, skip_reason, from_cache.
    """
    result = fetch_post_page(url, use_cache=True, save_to_cache=True)
    # Keep same keys UI expects; add content for resources
    return {
        "url_tried": result["url_tried"],
        "normalized_url": result["normalized_url"],
        "status_code": result["status_code"],
        "author": result["author"],
        "content": result.get("content") or "",
        "error": result["error"],
        "skip_reason": result["skip_reason"],
        "from_cache": result.get("from_cache", False),
    }


def get_posts_without_author(driver, limit: Optional[int] = None) -> list:
    """
    Fetch Post nodes that don't have author information yet.

    Args:
        driver: Neo4j driver
        limit: Optional limit on number of posts to fetch

    Returns:
        List of dicts with post URN and URL
    """
    query = """
    MATCH (post:Post)
    WHERE post.url IS NOT NULL
      AND post.url <> ''
      AND (post.author_profile_url IS NULL OR post.author_profile_url = '')
    RETURN post.urn as urn, post.url as url
    """

    if limit:
        query += f" LIMIT {limit}"

    with driver.session(database=NEO4J_DATABASE) as session:
        result = session.run(query)
        return [{"urn": record["urn"], "url": record["url"]} for record in result]


def update_post_author(driver, post_urn: str, author_info: Dict[str, str]):
    """
    Update a Post node with author information and create Person node with CREATES relationship.

    Creates or merges a Person node based on profile_url, then creates a CREATES
    relationship from the Person to the Post.

    Args:
        driver: Neo4j driver
        post_urn: URN of the post to update
        author_info: Dict with 'name' and 'profile_url'
    """
    query = """
    MATCH (post:Post {urn: $urn})
    SET post.author_name = $name,
        post.author_profile_url = $profile_url
    WITH post

    // Update existing Person node linked to this post (CREATES or REPOSTS)
    OPTIONAL MATCH (linked_person:Person)-[:CREATES|REPOSTS]->(post)
    FOREACH (_ IN CASE WHEN linked_person IS NULL THEN [] ELSE [1] END |
      SET linked_person.name = $name,
          linked_person.profile_url = $profile_url
    )

    // Create or merge Person node by profile_url (fallback)
    MERGE (person:Person {profile_url: $profile_url})
    ON CREATE SET person.name = $name
    ON MATCH SET person.name = $name

    // Create CREATES relationship
    MERGE (person)-[:CREATES]->(post)

    RETURN post.urn as urn, person.profile_url as person_url
    """
    with driver.session(database=NEO4J_DATABASE) as session:
        result = session.run(
            query,
            urn=post_urn,
            name=author_info["name"],
            profile_url=author_info["profile_url"],
        )
        return result.single() is not None


def main():
    """Main function to enrich posts with author profile information."""
    import sys

    print("🔍 LinkedIn Post Author Profile Enrichment")
    print("=" * 60)

    # Parse command line args
    limit = None
    if len(sys.argv) > 1 and sys.argv[1] == "--limit":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        print(f"⚠️  LIMIT MODE: Processing only first {limit} posts\n")

    # Connect to Neo4j
    print("🔌 Connecting to Neo4j...")
    print(f"   URI: {NEO4J_URI}")
    print(f"   Database: {NEO4J_DATABASE}")

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))

    try:
        driver.verify_connectivity()
        print("   ✅ Connected successfully\n")
    except Exception as e:
        print(f"   ❌ Connection failed: {e}")
        return

    # Fetch posts without author info
    print("🔍 Fetching posts without author information...")
    posts = get_posts_without_author(driver, limit=limit)
    print(f"✅ Found {len(posts)} posts to process\n")

    if not posts:
        print("✅ All posts already have author information!")
        driver.close()
        return

    # Process each post
    success_count = 0
    failed_count = 0

    for i, post in enumerate(posts, 1):
        print(f"[{i}/{len(posts)}] Processing: {post['urn']}")
        print(f"   URL: {post['url']}")

        # Extract author profile
        author_info = extract_author_profile(post["url"])

        if author_info:
            print(f"   ✅ Found author: {author_info['name']}")
            print(f"      Profile: {author_info['profile_url']}")

            # Update Neo4j
            if update_post_author(driver, post["urn"], author_info):
                print(f"   ✅ Updated Post node")
                success_count += 1
            else:
                print(f"   ⚠️  Failed to update Post node")
                failed_count += 1
        else:
            print(f"   ⚠️  Could not extract author profile")
            failed_count += 1

        print()

    # Summary
    print("=" * 60)
    print("📊 ENRICHMENT SUMMARY")
    print("=" * 60)
    print(f"Total posts processed: {len(posts)}")
    print(f"Successfully enriched: {success_count}")
    print(f"Failed: {failed_count}")
    print()

    if success_count > 0:
        print("✅ Posts now have author_name and author_profile_url properties!")
        print("✅ Person nodes created with CREATES relationships to posts!")
        print()
        print("💡 Query examples:")
        print("   # View all authors")
        print("   MATCH (person:Person)-[:CREATES]->(post:Post)")
        print("   RETURN person.name, count(post) as post_count")
        print("   ORDER BY post_count DESC")
        print()
        print("   # View posts by author")
        print("   MATCH (person:Person {name: 'Author Name'})-[:CREATES]->(post:Post)")
        print("   RETURN post.urn, post.url")

    driver.close()


if __name__ == "__main__":
    main()
