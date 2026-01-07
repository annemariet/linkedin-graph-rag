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

from neo4j import GraphDatabase


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

        # Remove 'www.' prefix for cleaner domain names
        if domain.startswith("www."):
            domain = domain[4:]

        # Determine resource type based on domain
        resource_type = "article"  # default

        # Video platforms
        if any(
            video_domain in domain
            for video_domain in ["youtube.com", "youtu.be", "vimeo.com"]
        ):
            resource_type = "video"
        # GitHub
        elif "github.com" in domain:
            resource_type = "repository"
        # Documentation sites
        elif any(
            doc_domain in domain
            for doc_domain in ["docs.", "documentation", "readthedocs.io"]
        ):
            resource_type = "documentation"
        # LinkedIn articles (treat as external)
        elif "linkedin.com" in domain and "/pulse/" in url:
            resource_type = "article"
        # Other article/blog platforms
        elif any(
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
        ):
            resource_type = "article"

        return {
            "domain": domain,
            "type": resource_type,
        }
    except Exception:
        return {"domain": None, "type": "unknown"}


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

    # Internal LinkedIn navigation links
    if url.startswith("https://www.linkedin.com/feed/") and "update" not in url:
        return True

    return False


def get_posts_with_content(driver, limit: Optional[int] = None) -> List[Dict[str, str]]:
    """
    Fetch Post nodes that have content text.

    Args:
        driver: Neo4j driver
        limit: Optional limit on number of posts to fetch

    Returns:
        List of dicts with post URN and content text
    """
    query = """
    MATCH (post:Post)
    WHERE post.content IS NOT NULL
      AND post.content <> ''
    RETURN post.urn as urn, post.content as text
    """

    if limit:
        query += f" LIMIT {limit}"

    with driver.session() as session:
        result = session.run(query)
        return [{"urn": record["urn"], "text": record["text"]} for record in result]


def get_comments_with_text(driver, limit: Optional[int] = None) -> List[Dict[str, str]]:
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

    with driver.session() as session:
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
            content = props.get("content", "")
            if content:
                urls = extract_urls_from_text(content)
                if urls:
                    resources["posts"][urn] = urls

        # Extract from Comment text
        elif "Comment" in labels:
            text = props.get("text", "")
            if text:
                urls = extract_urls_from_text(text)
                if urls:
                    resources["comments"][urn] = urls

    return resources


def create_resource_nodes_and_relationships(
    driver, source_urn: str, urls: List[str], source_type: str = "Post"
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

    for url in urls:
        if should_ignore_url(url):
            continue

        url_info = categorize_url(url)
        if not url_info["domain"]:
            continue

        query = f"""
        MATCH (source:{source_type} {{urn: $source_urn}})

        MERGE (resource:Resource {{url: $url}})
        ON CREATE SET resource.domain = $domain,
                      resource.type = $type

        MERGE (source)-[:REFERENCES]->(resource)

        RETURN resource.url as url
        """

        with driver.session() as session:
            result = session.run(
                query,
                source_urn=source_urn,
                url=url,
                domain=url_info["domain"],
                type=url_info["type"],
            )
            if result.single():
                created += 1

    return created


def enrich_posts_with_resources(driver, json_file: Optional[str] = None):
    """
    Extract resources from posts and comments, create Resource nodes.

    Args:
        driver: Neo4j driver
        json_file: Optional path to JSON file for full text extraction
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
        posts = get_posts_with_content(driver)
        comments = get_comments_with_text(driver)

        post_resources = {}
        for post in posts:
            urls = extract_urls_from_text(post["text"])
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
                driver, post_urn, urls, source_type="Post"
            )
            if count > 0:
                total_resources += count
                processed_posts += 1

    # Process comments
    if comment_resources:
        print(f"📊 Processing resources from {len(comment_resources)} comments...")
        for comment_urn, urls in comment_resources.items():
            count = create_resource_nodes_and_relationships(
                driver, comment_urn, urls, source_type="Comment"
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
