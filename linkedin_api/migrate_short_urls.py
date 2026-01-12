#!/usr/bin/env python3
"""
Migrate existing Resource nodes with short URLs to their final URLs.

This script finds Resources that are short URLs (like lnkd.in, bit.ly),
resolves their redirects, and updates the Resource nodes to use the final URLs.

Usage:
    uv run python -m linkedin_api.migrate_short_urls
"""

import os
import sys
from dotenv import load_dotenv
from neo4j import GraphDatabase

from linkedin_api.extract_resources import resolve_redirect

load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI") or "neo4j://localhost:7687"
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME") or "neo4j"
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD") or "password"
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE") or "neo4j"


def migrate_short_urls(driver, database: str = "neo4j", limit: int = None):
    """
    Migrate existing Resource nodes with short URLs to their final URLs.

    Args:
        driver: Neo4j driver
        database: Neo4j database name
        limit: Optional limit on number of Resources to process
    """
    print("\n🔄 Migrating short URLs to final URLs...")
    print("=" * 60)

    # Common short URL domains
    short_url_domains = [
        "lnkd.in",
        "bit.ly",
        "tinyurl.com",
        "short.link",
        "t.co",
        "goo.gl",
        "ow.ly",
        "buff.ly",
        "is.gd",
    ]

    with driver.session(database=database) as session:
        # Find Resources with potential short URLs
        query = """
        MATCH (resource:Resource)
        WHERE any(domain IN $short_domains WHERE resource.url CONTAINS domain)
        RETURN resource.url as url
        ORDER BY resource.url
        """

        if limit:
            query += f" LIMIT {limit}"

        result = session.run(query, short_domains=short_url_domains)
        resources = [record["url"] for record in result]

        if not resources:
            print("✅ No short URLs found to migrate")
            return

        print(f"📊 Found {len(resources)} potential short URLs to migrate\n")

        migrated = 0
        failed = 0
        skipped = 0

        for i, original_url in enumerate(resources, 1):
            if i % 10 == 0:
                print(
                    f"   Processing {i}/{len(resources)}... (migrated: {migrated}, failed: {failed}, skipped: {skipped})"
                )

            try:
                # Resolve redirect
                final_url = resolve_redirect(original_url)

                if final_url == original_url:
                    # No redirect or resolution failed, skip
                    skipped += 1
                    continue

                # Migrate the Resource - single query approach
                migrate_query = """
                MATCH (oldResource:Resource {url: $original_url})
                OPTIONAL MATCH (source)-[ref:REFERENCES]->(oldResource)
                WITH oldResource, collect(DISTINCT source) as sources

                // Create or merge Resource with final URL
                MERGE (newResource:Resource {url: $final_url})
                ON CREATE SET newResource.domain = oldResource.domain,
                              newResource.type = oldResource.type,
                              newResource.title = oldResource.title
                ON MATCH SET newResource.domain = COALESCE(newResource.domain, oldResource.domain),
                            newResource.type = COALESCE(newResource.type, oldResource.type),
                            newResource.title = COALESCE(newResource.title, oldResource.title)

                // Migrate all REFERENCES relationships
                WITH newResource, sources, oldResource
                UNWIND CASE WHEN sources IS NOT NULL THEN sources ELSE [] END as source
                WHERE source IS NOT NULL
                MERGE (source)-[:REFERENCES]->(newResource)

                // Delete old Resource and return count
                WITH DISTINCT oldResource
                DELETE oldResource
                RETURN 1 as migrated
                """

                result = session.run(
                    migrate_query, original_url=original_url, final_url=final_url
                )
                record = result.single()

                if record and record["migrated"] > 0:
                    migrated += 1
                    if (i - 1) % 10 != 0:  # Don't print if we just printed progress
                        print(f"   ✅ {original_url[:60]} → {final_url[:60]}")
                else:
                    failed += 1
                    print(f"   ⚠️  Failed to migrate: {original_url[:60]}")

            except Exception as e:
                failed += 1
                print(f"   ❌ Error processing {original_url[:60]}: {str(e)}")
                continue

        print("\n" + "=" * 60)
        print("📊 MIGRATION SUMMARY")
        print("=" * 60)
        print(f"Total short URLs found: {len(resources)}")
        print(f"✅ Successfully migrated: {migrated}")
        print(f"⚠️  Failed: {failed}")
        print(f"⏭️  Skipped (no redirect): {skipped}")
        print()


def main():
    """Main function to run the migration."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Migrate Resource nodes with short URLs to final URLs"
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
        migrate_short_urls(driver, database=args.database, limit=args.limit)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
