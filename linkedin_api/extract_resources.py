#!/usr/bin/env python3
"""
Extract external resources (URLs) from post and comment content.

Extracts URLs from:
- Post commentary (author's text)
- Comment text

Creates Resource nodes with REFERENCES relationships to posts and comments.
"""

import re
from typing import Dict, List, Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from neo4j import GraphDatabase


def _is_comment_feed_url(url: str) -> bool:
    """True if URL is a feed/update with a comment URN (not a post); such URLs don't return post content."""
    return bool(url and "urn:li:comment:" in url)


def fetch_post_content_from_url(url: str) -> Optional[str]:
    """
    Fetch full post content from a LinkedIn post URL.

    Args:
        url: LinkedIn post URL (must be a post URN in the path, not a comment URN)

    Returns:
        Extracted text content or None if extraction fails
    """
    try:
        response = requests.get(url, timeout=10, allow_redirects=True)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # Try to find post content - LinkedIn uses various selectors
        content_selectors = [
            "article[data-id]",
            ".feed-shared-update-v2__description",
            ".feed-shared-text",
            '[data-test-id="main-feed-activity-card"]',
        ]

        content_text = []

        # Try each selector
        for selector in content_selectors:
            elements = soup.select(selector)
            if elements:
                for elem in elements:
                    text = elem.get_text(strip=True)
                    if text and len(text) > 20:  # Filter out very short text
                        content_text.append(text)

        # Fallback: extract from meta tags
        if not content_text:
            og_description = soup.find("meta", property="og:description")
            if og_description:
                content_text.append(og_description.get("content", ""))

            # Try title as fallback
            title = soup.find("title")
            if title:
                title_text = title.get_text(strip=True)
                # LinkedIn titles often contain post content before " | "
                if " | " in title_text:
                    content_text.append(title_text.split(" | ")[0])

        if content_text:
            return "\n".join(content_text)

        return None
    except Exception:
        return None


def extract_urls_from_text(text: str) -> List[str]:
    """
    Extract all URLs from text using regex.

    Args:
        text: Text content to search for URLs

    Returns:
        List of unique URLs found
    """
    if not text:
        return []

    # URL pattern - matches http/https URLs
    url_pattern = r"https?://[^\s<>\"'{}|\\^`\[\]]+[^\s<>\"'{}|\\^`\[\].,;:!?]"
    urls = re.findall(url_pattern, text)

    # Clean up URLs (remove trailing punctuation that might have been captured)
    cleaned_urls = []
    for url in urls:
        # Remove trailing punctuation
        url = url.rstrip(".,;:!?)")
        # Ensure URL is valid
        try:
            parsed = urlparse(url)
            if parsed.netloc:  # Has a valid domain
                cleaned_urls.append(url)
        except Exception:
            continue

    return list(set(cleaned_urls))  # Return unique URLs


def categorize_url(url: str) -> Dict[str, Optional[str]]:
    """
    Categorize a URL by domain and type.

    Args:
        url: URL to categorize

    Returns:
        Dict with 'domain', 'type', and optionally 'title'
    """
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        path = parsed.path.lower()

        # Remove 'www.' prefix for cleaner domain names
        if domain.startswith("www."):
            domain = domain[4:]

        # First, check file extensions in URL path
        url_lower = url.lower()
        file_extensions = {
            # Documents
            ".pdf": "document",
            ".doc": "document",
            ".docx": "document",
            ".ppt": "presentation",
            ".pptx": "presentation",
            ".xls": "spreadsheet",
            ".xlsx": "spreadsheet",
            # Images
            ".jpg": "image",
            ".jpeg": "image",
            ".png": "image",
            ".gif": "image",
            ".svg": "image",
            ".webp": "image",
            # Videos
            ".mp4": "video",
            ".avi": "video",
            ".mov": "video",
            ".webm": "video",
            ".mkv": "video",
            # Audio
            ".mp3": "audio",
            ".wav": "audio",
            ".ogg": "audio",
            # Archives
            ".zip": "archive",
            ".tar": "archive",
            ".gz": "archive",
        }

        for ext, resource_type in file_extensions.items():
            if ext in url_lower:
                return {"domain": domain, "type": resource_type}

        # Determine resource type based on domain and path patterns
        resource_type = None

        # Video platforms
        if any(
            video_domain in domain
            for video_domain in [
                "youtube.com",
                "youtu.be",
                "vimeo.com",
                "dailymotion.com",
                "twitch.tv",
            ]
        ):
            resource_type = "video"
        # Code repositories
        elif any(
            repo_domain in domain
            for repo_domain in [
                "github.com",
                "gitlab.com",
                "bitbucket.org",
                "sourceforge.net",
            ]
        ):
            resource_type = "repository"
        # Documentation sites
        elif any(
            doc_domain in domain
            for doc_domain in ["docs.", "documentation", "readthedocs.io", "gitbook.io"]
        ):
            resource_type = "documentation"
        # Social media (treat as external content)
        elif any(
            social_domain in domain
            for social_domain in [
                "twitter.com",
                "x.com",
                "facebook.com",
                "instagram.com",
                "tiktok.com",
            ]
        ):
            resource_type = "social"
        # News and articles
        elif (
            any(
                article_domain in domain
                for article_domain in [
                    "medium.com",
                    "substack.com",
                    "dev.to",
                    "hashnode.com",
                    "blog.",
                    "news.",
                    "article",
                ]
            )
            or "/blog/" in path
            or "/article/" in path
            or "/post/" in path
        ):
            resource_type = "article"
        # Academic/research
        elif any(
            academic_domain in domain
            for academic_domain in [
                "arxiv.org",
                "scholar.google.com",
                "researchgate.net",
                "academia.edu",
                "doi.org",
            ]
        ):
            resource_type = "research"
        # E-commerce
        elif any(
            shop_domain in domain
            for shop_domain in ["amazon.com", "shopify.com", "etsy.com", "ebay.com"]
        ):
            resource_type = "product"
        # Tools/platforms
        elif any(
            tool_domain in domain
            for tool_domain in [
                "stackoverflow.com",
                "reddit.com",
                "discord.com",
                "slack.com",
                "notion.so",
                "figma.com",
            ]
        ):
            resource_type = "tool"
        # Podcasts
        elif any(
            podcast_domain in domain
            for podcast_domain in ["spotify.com", "podcast", "anchor.fm", "podbean.com"]
        ):
            resource_type = "podcast"
        # LinkedIn articles (treat as external)
        elif "linkedin.com" in domain and "/pulse/" in url:
            resource_type = "article"

        # Default to "article" if no specific type found
        # This is reasonable since most web URLs are articles/blog posts
        if resource_type is None:
            resource_type = "article"

        return {
            "domain": domain,
            "type": resource_type,
        }
    except Exception:
        return {"domain": None, "type": "unknown"}


def resolve_redirect(url: str, max_redirects: int = 5) -> str:
    """
    Resolve redirects to get the final URL.

    Handles LinkedIn short URLs (lnkd.in) which use an intermediate page.
    For LinkedIn URLs, parses the HTML to extract the final destination.

    Args:
        url: URL to resolve
        max_redirects: Maximum number of redirects to follow

    Returns:
        Final URL after following redirects, or original URL if resolution fails
    """
    # Use User-Agent to avoid being blocked
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    # Special handling for LinkedIn short URLs
    if "lnkd.in" in url:
        try:
            # LinkedIn short URLs require GET request and HTML parsing
            response = requests.get(
                url,
                timeout=15,
                allow_redirects=True,
                headers=headers,
            )

            # Check if we got redirected via HTTP (some lnkd.in URLs redirect directly)
            if response.url != url and "lnkd.in" not in response.url:
                return response.url

            # LinkedIn shows intermediate page - parse HTML for final URL
            soup = BeautifulSoup(response.text, "html.parser")

            # Pattern 1: Look for meta tags with the final URL
            meta_refresh = soup.find("meta", attrs={"http-equiv": "refresh"})
            if meta_refresh and meta_refresh.get("content"):
                content = meta_refresh["content"]
                # Extract URL from refresh meta tag: "0;url=https://..."
                url_match = re.search(r"url=(https?://[^\s]+)", content, re.IGNORECASE)
                if url_match:
                    return url_match.group(1)

            # Pattern 2: Look for the final URL in the page text
            # LinkedIn shows it in the page content, often in a specific format
            page_text = response.text

            # Look for URLs that are not LinkedIn domains
            # Simple pattern that matches any http/https URL
            simple_pattern = (
                r"https?://[^\s<>\"'{}|\\^`\[\]]+[^\s<>\"'{}|\\^`\[\].,;:!?]"
            )
            all_urls = re.findall(simple_pattern, page_text)

            # Filter out LinkedIn URLs and static assets, prioritize content URLs
            external_urls = []
            for found_url in all_urls:
                found_url = found_url.rstrip(".,;:!?)")
                url_lower = found_url.lower()

                # Skip LinkedIn domains
                if "linkedin.com" in url_lower or "lnkd.in" in url_lower:
                    continue

                # Skip static asset patterns (CDN, static files)
                if any(
                    pattern in url_lower
                    for pattern in [
                        "/static/",
                        "/aero-v1/",
                        ".ico",
                        ".png",
                        ".jpg",
                        ".css",
                        ".js",
                    ]
                ):
                    continue

                # Must be a valid-looking URL
                if found_url.startswith("http") and len(found_url) > 15:
                    external_urls.append(found_url)

            # Return the first external URL found (should be the final destination)
            if external_urls:
                return external_urls[0]

            # Pattern 3: Look for links in the page
            links = soup.find_all("a", href=True)
            for link in links:
                href = link.get("href", "")
                if (
                    href.startswith("http")
                    and "linkedin.com" not in href
                    and "lnkd.in" not in href
                ):
                    return href

            # If HTTP redirect worked, use that
            if response.url != url:
                return response.url

        except Exception:
            # Log error for debugging but continue
            pass

        # If LinkedIn-specific handling failed, return original
        return url

    # For non-LinkedIn URLs, try standard redirect resolution
    # Try HEAD first (faster)
    try:
        response = requests.head(
            url,
            timeout=15,
            allow_redirects=True,
            headers=headers,
        )
        final_url = response.url
        if final_url != url:
            return final_url
    except Exception:
        pass

    # If HEAD fails or returns same URL, try GET (some servers don't support HEAD)
    try:
        response = requests.get(
            url,
            timeout=15,
            allow_redirects=True,
            stream=True,
            headers=headers,
        )
        final_url = response.url
        if final_url != url:
            return final_url
    except Exception:
        pass

    # If both fail, return original URL
    return url


def extract_title_from_url(url: str) -> Optional[str]:
    """
    Extract title from a URL by fetching the page and parsing HTML.

    Args:
        url: URL to extract title from

    Returns:
        Title string or None if extraction fails
    """
    try:
        response = requests.get(url, timeout=10, allow_redirects=True)
        response.raise_for_status()

        # Check content type
        content_type = response.headers.get("content-type", "").lower()
        if "text/html" not in content_type:
            return None

        soup = BeautifulSoup(response.text, "html.parser")

        # Try <title> tag first
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text(strip=True)
            if title:
                return title

        # Try Open Graph title
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            return og_title["content"].strip()

        # Try Twitter Card title
        twitter_title = soup.find("meta", attrs={"name": "twitter:title"})
        if twitter_title and twitter_title.get("content"):
            return twitter_title["content"].strip()

        return None
    except Exception:
        return None


def should_ignore_url(url: str) -> bool:
    """
    Check if URL should be ignored (hashtags, profile links, etc.).

    Args:
        url: URL to check

    Returns:
        True if URL should be ignored
    """
    # LinkedIn profile links (already handled via Person nodes)
    if "linkedin.com/in/" in url or "linkedin.com/pub/" in url:
        return True

    # Hashtag links (LinkedIn hashtag pages)
    if "linkedin.com/feed/hashtag/" in url:
        return True

    # LinkedIn company pages (could be handled separately if needed)
    if "linkedin.com/company/" in url:
        return True

    # Internal LinkedIn navigation links (including feed update URLs)
    if url.startswith("https://www.linkedin.com/feed/"):
        return True

    return False


def get_posts_with_content(
    driver, limit: Optional[int] = None, database: str = "neo4j"
) -> List[Dict[str, str]]:
    """
    Fetch Post nodes that have content text or URL.

    Args:
        driver: Neo4j driver
        limit: Optional limit on number of posts to fetch

    Returns:
        List of dicts with post URN, content text, and URL
    """
    query = """
    MATCH (post:Post)
    WHERE (post.content IS NOT NULL AND post.content <> '')
       OR (post.url IS NOT NULL AND post.url <> '')
    RETURN post.urn as urn, post.content as text, post.url as url
    """

    if limit:
        query += f" LIMIT {limit}"

    with driver.session(database=database) as session:
        result = session.run(query)
        return [
            {
                "urn": record["urn"],
                "text": record["text"],
                "url": record["url"],
            }
            for record in result
        ]


def get_comments_with_text(
    driver, limit: Optional[int] = None, database: str = "neo4j"
) -> List[Dict[str, str]]:
    """
    Fetch Comment nodes that have text content.

    Args:
        driver: Neo4j driver
        limit: Optional limit on number of comments to fetch

    Returns:
        List of dicts with comment URN and text
    """
    query = """
    MATCH (comment:Comment)
    WHERE comment.text IS NOT NULL
      AND comment.text <> ''
    RETURN comment.urn as urn, comment.text as text
    """

    if limit:
        query += f" LIMIT {limit}"

    with driver.session(database=database) as session:
        result = session.run(query)
        return [{"urn": record["urn"], "text": record["text"]} for record in result]


def extract_resources_from_json(json_file: str) -> Dict[str, Dict[str, List[str]]]:
    """
    Extract resources from the original JSON data file.

    This is useful when text is truncated in Neo4j.

    Args:
        json_file: Path to the neo4j_data JSON file

    Returns:
        Dict with 'posts' and 'comments' keys, each mapping URN -> list of URLs
    """
    import json

    resources = {"posts": {}, "comments": {}}

    with open(json_file, "r") as f:
        data = json.load(f)

    nodes = data.get("nodes", [])
    for node in nodes:
        labels = node.get("labels", [])
        props = node.get("properties", {})
        urn = props.get("urn")

        if not urn:
            continue

        # Extract from Post content
        if "Post" in labels:
            # Prefer extracted_urls (from full content) if available
            urls = props.get("extracted_urls", [])
            if not urls:
                # Fallback 1: extract from truncated content
                content = props.get("content", "")
                is_truncated = False
                if content:
                    urls = extract_urls_from_text(content)
                    # Check if content seems truncated
                    is_truncated = len(content) == 200 or (
                        len(content) > 190
                        and not content.endswith((".", "!", "?", "…"))
                    )
                # Fallback 2: fetch from post URL if no URLs found or content seems truncated
                if not urls or is_truncated:
                    post_url = props.get("url", "")
                    if post_url and not _is_comment_feed_url(post_url):
                        print(f"   🔄 Fetching content from post URL: {post_url}")
                        full_content = fetch_post_content_from_url(post_url)
                        if full_content:
                            urls = extract_urls_from_text(full_content)
            if urls:
                resources["posts"][urn] = urls

        # Extract from Comment text
        elif "Comment" in labels:
            # Prefer extracted_urls (from full content) if available
            urls = props.get("extracted_urls", [])
            if not urls:
                # Fallback: extract from truncated text
                # Note: Comments don't have URLs, so we can't fetch them
                text = props.get("text", "")
                if text:
                    urls = extract_urls_from_text(text)
            if urls:
                resources["comments"][urn] = urls

    return resources


def create_resource_nodes_and_relationships(
    driver,
    source_urn: str,
    urls: List[str],
    source_type: str = "Post",
    database: str = "neo4j",
) -> int:
    """
    Create Resource nodes and REFERENCES relationships.

    Args:
        driver: Neo4j driver
        source_urn: URN of the source (Post or Comment)
        urls: List of URLs to create as resources
        source_type: Type of source node ("Post" or "Comment")

    Returns:
        Number of resources created
    """
    created = 0

    # Use a single session for all operations to avoid connection issues
    try:
        with driver.session(database=database) as session:
            for url in urls:
                if should_ignore_url(url):
                    continue

                try:
                    # Resolve redirects to get final URL
                    url = resolve_redirect(url)

                    url_info = categorize_url(url)
                    if not url_info["domain"]:
                        continue

                    # Extract title from URL
                    title = extract_title_from_url(url)

                    # Build SET clauses conditionally
                    create_set = "resource.domain = $domain, resource.type = $type"
                    match_set = "resource.domain = $domain, resource.type = $type"

                    params = {
                        "source_urn": source_urn,
                        "url": url,
                        "domain": url_info["domain"],
                        "type": url_info["type"],
                    }

                    if title:
                        create_set += ", resource.title = $title"
                        match_set += ", resource.title = $title"
                        params["title"] = title

                    query = f"""
                    MATCH (source:{source_type} {{urn: $source_urn}})
                    MERGE (resource:Resource {{url: $url}})
                    ON CREATE SET {create_set}
                    ON MATCH SET {match_set}
                    MERGE (source)-[:REFERENCES]->(resource)
                    RETURN resource.url as url, source.urn as source_urn
                    """

                    result = session.run(query, **params)
                    record = result.single()
                    if record:
                        created += 1
                    else:
                        # Source node not found - this shouldn't happen but log it
                        print(
                            f"   ⚠️  Source {source_type} node not found: {source_urn}"
                        )
                except Exception as e:
                    # Log error but continue with next URL
                    print(f"   ⚠️  Error processing URL {url}: {str(e)}")
                    continue
    except Exception as e:
        print(f"   ❌ Error creating session for {source_urn}: {str(e)}")
        raise

    return created


def enrich_posts_with_resources(
    driver, json_file: Optional[str] = None, database: str = "neo4j"
):
    """
    Extract resources from posts and comments, create Resource nodes.

    Args:
        driver: Neo4j driver
        json_file: Optional path to JSON file for full text extraction
        database: Neo4j database name
    """
    print("\n🔍 Extracting external resources from posts and comments...")

    # Extract from JSON file if provided (has full text, not truncated)
    if json_file:
        print(f"📂 Extracting from JSON file: {json_file}")
        all_resources = extract_resources_from_json(json_file)
        post_resources = all_resources.get("posts", {})
        comment_resources = all_resources.get("comments", {})
        print(
            f"✅ Found resources in {len(post_resources)} posts and {len(comment_resources)} comments from JSON"
        )
    else:
        # Extract from Neo4j (may be truncated)
        posts = get_posts_with_content(driver, database=database)
        comments = get_comments_with_text(driver, database=database)

        post_resources = {}
        for post in posts:
            # Try extracting from stored content first
            urls = []
            content = post.get("text", "")
            if content:
                urls = extract_urls_from_text(content)
                # Check if content seems truncated (exactly 200 chars or ends abruptly)
                is_truncated = len(content) == 200 or (
                    len(content) > 190 and not content.endswith((".", "!", "?", "…"))
                )
            else:
                is_truncated = True

            # Fallback: fetch from post URL if no URLs found or content seems truncated
            post_url = post.get("url")
            if (not urls or is_truncated) and post_url and not _is_comment_feed_url(post_url):
                print(f"   🔄 Fetching content from post URL: {post_url}")
                full_content = fetch_post_content_from_url(post_url)
                if full_content:
                    urls = extract_urls_from_text(full_content)
            if urls:
                post_resources[post["urn"]] = urls

        comment_resources = {}
        for comment in comments:
            urls = extract_urls_from_text(comment["text"])
            if urls:
                comment_resources[comment["urn"]] = urls

        print(
            f"📊 Found {len(posts)} posts and {len(comments)} comments with text in Neo4j"
        )

    if not post_resources and not comment_resources:
        print("✅ No posts or comments with resources found!\n")
        return

    total_resources = 0
    processed_posts = 0
    processed_comments = 0

    # Process posts
    if post_resources:
        print(f"📊 Processing resources from {len(post_resources)} posts...")
        for post_urn, urls in post_resources.items():
            count = create_resource_nodes_and_relationships(
                driver, post_urn, urls, source_type="Post", database=database
            )
            if count > 0:
                total_resources += count
                processed_posts += 1

    # Process comments
    if comment_resources:
        print(f"📊 Processing resources from {len(comment_resources)} comments...")
        for comment_urn, urls in comment_resources.items():
            count = create_resource_nodes_and_relationships(
                driver, comment_urn, urls, source_type="Comment", database=database
            )
            if count > 0:
                total_resources += count
                processed_comments += 1

    print(
        f"✅ Created {total_resources} resource nodes from {processed_posts} posts and {processed_comments} comments"
    )
    print()


if __name__ == "__main__":
    import os
    import sys
    from dotenv import load_dotenv

    load_dotenv()

    NEO4J_URI = os.getenv("NEO4J_URI") or "neo4j://localhost:7687"
    NEO4J_USERNAME = os.getenv("NEO4J_USERNAME") or "neo4j"
    NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD") or "password"
    NEO4J_DATABASE = os.getenv("NEO4J_DATABASE") or "neo4j"

    json_file = sys.argv[1] if len(sys.argv) > 1 else None

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))

    try:
        driver.verify_connectivity()
        enrich_posts_with_resources(driver, json_file=json_file)
    finally:
        driver.close()
