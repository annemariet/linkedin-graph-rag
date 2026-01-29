#!/usr/bin/env python3
"""
Enrich Post nodes with author profile information by scraping LinkedIn URLs.

Extracts author name and profile URL from post HTML and stores them as properties
on the Post nodes in Neo4j.
"""

import os
import json
import time
from typing import Dict, Optional

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI") or "neo4j://localhost:7687"
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME") or "neo4j"
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD") or "password"
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE") or "neo4j"

# region agent log
_AGENT_LOG_PATH = "/Users/lucy/Dev/amai-lab/projects/linkedin/.cursor/debug.log"


def _agent_log(
    *, run_id: str, hypothesis_id: str, location: str, message: str, data: dict
):
    try:
        with open(_AGENT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "sessionId": "debug-session",
                        "runId": run_id,
                        "hypothesisId": hypothesis_id,
                        "location": location,
                        "message": message,
                        "data": data,
                        "timestamp": int(time.time() * 1000),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    except Exception:
        pass


# endregion


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
    try:
        response = requests.get(url, timeout=10, allow_redirects=True)
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
    _agent_log(
        run_id="pre-fix",
        hypothesis_id="H1",
        location="linkedin_api/enrich_profiles.py:update_post_author:entry",
        message="update_post_author called",
        data={
            "post_urn_prefix": post_urn[:32] if isinstance(post_urn, str) else None,
            "has_name": bool(author_info.get("name")),
            "has_profile_url": bool(author_info.get("profile_url")),
            "profile_url_prefix": (author_info.get("profile_url") or "")[:32],
        },
    )
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
    _agent_log(
        run_id="pre-fix",
        hypothesis_id="H1",
        location="linkedin_api/enrich_profiles.py:update_post_author:before_run",
        message="Running Cypher to update post author",
        data={
            "query_first_10_lines": "\n".join(query.strip("\n").splitlines()[:10]),
            "contains_with_post": "WITH post" in query,
        },
    )

    with driver.session(database=NEO4J_DATABASE) as session:
        try:
            result = session.run(
                query,
                urn=post_urn,
                name=author_info["name"],
                profile_url=author_info["profile_url"],
            )
            ok = result.single() is not None
            _agent_log(
                run_id="pre-fix",
                hypothesis_id="H1",
                location="linkedin_api/enrich_profiles.py:update_post_author:after_run",
                message="Cypher executed",
                data={"ok": ok},
            )
            return ok
        except Exception as e:
            _agent_log(
                run_id="pre-fix",
                hypothesis_id="H1",
                location="linkedin_api/enrich_profiles.py:update_post_author:error",
                message="Cypher execution failed",
                data={"error_type": type(e).__name__, "error": str(e)[:200]},
            )
            raise


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
