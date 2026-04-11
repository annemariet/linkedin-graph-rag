#!/usr/bin/env python3
"""
Enrich Post nodes with author profile information using post URLs from the Portability API.

.. deprecated::
    This module is superseded by ``enrich_graph.py`` which uses SimpleKGPipeline
    for LLM-powered enrichment. This module is kept for backward compatibility.

Extracts author name and profile URL from post HTML and stores them as properties
on the Post nodes in Neo4j. Post URLs come from the Portability API (your changelog).
Optional: can fetch once per URL and parse author + post content from the same HTML;
optionally cache raw HTML for reuse. Disable with ENABLE_AUTHOR_ENRICHMENT=0.
"""

import hashlib
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from neo4j import GraphDatabase

from linkedin_api.utils.post_html import (
    linkedin_http_fetch_is_blocked,
    parse_post_author_from_soup,
)
from linkedin_api.utils.urns import comment_urn_to_post_url

logger = logging.getLogger(__name__)

load_dotenv()

# When unset or 0/false/no, author enrichment (reading post URLs from the API for author name/URL) is skipped.
ENABLE_AUTHOR_ENRICHMENT = os.getenv("ENABLE_AUTHOR_ENRICHMENT", "1").lower() not in (
    "0",
    "false",
    "no",
)


def is_author_enrichment_enabled() -> bool:
    """Return True if author profile enrichment (reading post URLs from the API) is enabled."""
    return ENABLE_AUTHOR_ENRICHMENT


# Dir for caching fetched HTML (optional): outputs/review/cache/
_CACHE_DIR: Path | bool | None = None


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
    return _CACHE_DIR if isinstance(_CACHE_DIR, Path) else None


def _url_to_cache_key(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:32]


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
    meta = parse_post_author_from_soup(soup)
    name = (meta.get("post_author") or "").strip()
    profile_url = (meta.get("post_author_url") or "").strip()
    if name and 1 < len(name) < 200:
        return {"name": name, "profile_url": profile_url}
    return None


def _normalize_profile_link(link) -> Optional[Dict[str, str]]:
    """Extract name and profile_url from a single profile link (a tag with /in/)."""
    href = link.get("href", "")
    if "/in/" not in href:
        return None
    profile_url = href.split("?")[0]
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


def parse_comment_author_from_html(
    html: str, comment_text: str
) -> Optional[Dict[str, str]]:
    """
    Find the comment block in post HTML by matching comment text and extract author.

    Args:
        html: Raw post page HTML
        comment_text: Text of the comment to find (can be truncated)

    Returns:
        Dict with 'name' and 'profile_url' or None
    """
    if not comment_text or not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    snippet = (comment_text.strip()[:150] if comment_text else "").strip()
    if len(snippet) < 3:
        return None
    for elem in soup.find_all(True):
        if snippet[:50] in elem.get_text():
            for link in elem.find_all("a", href=True):
                if "/in/" in str(link.get("href", "")):
                    author = _normalize_profile_link(link)
                    if author:
                        return author
            parent = elem.parent
            while parent and parent.name:
                for link in parent.find_all("a", href=True):
                    if "/in/" in str(link.get("href", "")):
                        author = _normalize_profile_link(link)
                        if author:
                            return author
                parent = parent.parent
            break
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
        content_text.append(str(og["content"]))
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
    out: Dict[str, Any] = {
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
            if linkedin_http_fetch_is_blocked(normalized, raw):
                try:
                    cached_path.unlink(missing_ok=True)
                except OSError:
                    pass
                out["error"] = (
                    "Cached HTML was LinkedIn login/signup page; cache entry removed."
                )
                out["html"] = None
                return out
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
        if linkedin_http_fetch_is_blocked(response.url, raw):
            out["error"] = (
                "LinkedIn returned login/signup page instead of public post HTML."
            )
            out["content"] = ""
            out["author"] = None
            return out
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
            href = str(link["href"])
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


def get_comments_without_author(driver, limit: Optional[int] = None) -> list:
    """Fetch Comment nodes that have a url but no author_profile_url."""
    query = """
    MATCH (comment:Comment)
    WHERE comment.url IS NOT NULL
      AND (comment.author_profile_url IS NULL OR comment.author_name IS NULL)
    OPTIONAL MATCH (p:Person)-[:CREATES]->(comment)
    WITH comment, p
    WHERE p IS NULL OR p.profile_url IS NULL
    RETURN comment.urn AS urn, comment.url AS url, comment.text AS text
    """
    if limit:
        query += f" LIMIT {int(limit)}"
    with driver.session() as session:
        result = session.run(query)
        return [dict(record) for record in result]


def update_comment_author(
    driver, comment_urn: str, author_info: Dict[str, str]
) -> bool:
    """Set comment author; remove any existing incorrect CREATES and merge correct one."""
    query = """
    MATCH (comment:Comment {urn: $urn})
    OPTIONAL MATCH (any_person:Person)-[r:CREATES]->(comment)
    WITH comment, r
    DELETE r
    WITH comment
    SET comment.author_name = $name,
        comment.author_profile_url = $profile_url
    MERGE (person:Person {profile_url: $profile_url})
    ON CREATE SET person.name = $name
    ON MATCH SET person.name = $name
    MERGE (person)-[:CREATES]->(comment)
    RETURN comment.urn as urn
    """
    with driver.session() as session:
        result = session.run(
            query,
            urn=comment_urn,
            name=author_info.get("name", ""),
            profile_url=author_info["profile_url"],
        )
        return result.single() is not None


def enrich_comments_with_authors(driver, limit: Optional[int] = None) -> None:
    """Fetch comments without author, scrape post page, extract author, update Neo4j."""
    comments = get_comments_without_author(driver, limit)
    if not comments:
        logger.info("No comments need author enrichment")
        return
    logger.info("Enriching %d comments with authors...", len(comments))
    success = 0
    failed = 0
    for comment in comments:
        urn = comment["urn"]
        url = comment.get("url", "")
        text = comment.get("text", "")
        post_url = _normalize_post_url(url)
        if not post_url:
            continue
        result = fetch_post_page(post_url, use_cache=True, save_to_cache=True)
        html = result.get("html")
        if not html:
            continue
        author = parse_comment_author_from_html(html, text)
        if author:
            ok = update_comment_author(driver, urn, author)
            if ok:
                success += 1
            else:
                failed += 1
    if success or failed:
        logger.info("Comment author enrichment: %s ok, %s failed", success, failed)


def main():
    """Main function to enrich posts with author profile information."""
    import sys

    print("🔍 LinkedIn Post Author Profile Enrichment")
    print("=" * 60)

    if not ENABLE_AUTHOR_ENRICHMENT:
        print("⏭️  Author enrichment is disabled (ENABLE_AUTHOR_ENRICHMENT=0).")
        print(
            "   Set ENABLE_AUTHOR_ENRICHMENT=1 to fetch author name/profile from post URLs."
        )
        return

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
