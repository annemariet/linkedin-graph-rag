#!/usr/bin/env python3
"""
Re-classify all Resource nodes with updated domain and type based on their URLs.

This script re-categorizes all Resource nodes to ensure they have the correct
domain and type based on their current URL (after any migrations).

Usage:
    uv run python -m linkedin_api.reclassify_resources
"""

import os
import sys
from dotenv import load_dotenv
from neo4j import GraphDatabase

from linkedin_api.extract_resources import categorize_url, extract_title_from_url

load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI") or "neo4j://localhost:7687"
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME") or "neo4j"
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD") or "password"
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE") or "neo4j"


def reclassify_resources(driver, database: str = "neo4j", limit: int = None):
    """
    Re-classify all Resource nodes with updated domain and type.

    Args:
        driver: Neo4j driver
        database: Neo4j database name
        limit: Optional limit on number of Resources to process
    """
    print("\n🔄 Re-classifying all Resource nodes...")
    print("=" * 60)

    with driver.session(database=database) as session:
        # Find all Resources
        query = """
        MATCH (resource:Resource)
        RETURN resource.url as url
        ORDER BY resource.url
        """

        if limit:
            query += f" LIMIT {limit}"

        result = session.run(query)
        resources = [record["url"] for record in result]

        if not resources:
            print("✅ No Resources found to re-classify")
            return

        print(f"📊 Found {len(resources)} Resources to re-classify\n")

        updated = 0
        failed = 0
        unchanged = 0

        for i, url in enumerate(resources, 1):
            if i % 10 == 0:
                print(
                    f"   Processing {i}/{len(resources)}... "
                    f"(updated: {updated}, failed: {failed}, unchanged: {unchanged})"
                )

            try:
                # Re-categorize based on current URL
                url_info = categorize_url(url)
                new_domain = url_info.get("domain")
                new_type = url_info.get("type", "article")
                new_title = extract_title_from_url(url)

                if not new_domain:
                    failed += 1
                    if i <= 5:
                        print(f"   ⚠️  Could not categorize: {url[:60]}")
                    continue

                # Update the Resource with new classification
                update_query = """
                MATCH (resource:Resource {url: $url})
                WITH resource,
                     CASE WHEN resource.domain <> $new_domain OR resource.type <> $new_type
                     THEN 1 ELSE 0 END as needs_update
                SET resource.domain = $new_domain,
                    resource.type = $new_type,
                    resource.title = COALESCE($new_title, resource.title)
                RETURN needs_update
                """

                result = session.run(
                    update_query,
                    url=url,
                    new_domain=new_domain,
                    new_type=new_type,
                    new_title=new_title,
                )
                record = result.single()

                if record and record.get("needs_update", 0) > 0:
                    updated += 1
                    if (i - 1) % 10 != 0:
                        print(f"   ✅ {url[:50]} → {new_type} ({new_domain[:30]})")
                else:
                    unchanged += 1

            except Exception as e:
                failed += 1
                error_msg = str(e)
                if hasattr(e, "message"):
                    error_msg = e.message
                elif hasattr(e, "__class__"):
                    error_msg = f"{e.__class__.__name__}: {str(e)}"
                print(f"   ❌ Error processing {url[:60]}: {error_msg}")
                continue

        print("\n" + "=" * 60)
        print("📊 RE-CLASSIFICATION SUMMARY")
        print("=" * 60)
        print(f"Total Resources found: {len(resources)}")
        print(f"✅ Updated: {updated}")
        print(f"⏭️  Unchanged: {unchanged}")
        print(f"⚠️  Failed: {failed}")
        print()


def main():
    """Main function to run the re-classification."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Re-classify all Resource nodes with updated domain and type"
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of Resources to process (for testing)",
    )
    parser.add_argument(
        "--database",
        type=str,
        default=NEO4J_DATABASE,
        help=f"Neo4j database name (default: {NEO4J_DATABASE})",
    )

    args = parser.parse_args()

    print("🔌 Connecting to Neo4j...")
    print(f"   URI: {NEO4J_URI}")
    print(f"   Database: {args.database}")

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))

    try:
        driver.verify_connectivity()
        print("   ✅ Connected successfully\n")
    except Exception as e:
        print(f"   ❌ Connection failed: {e}")
        sys.exit(1)

    try:
        reclassify_resources(driver, database=args.database, limit=args.limit)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
