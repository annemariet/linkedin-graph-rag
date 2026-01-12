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
                    # No redirect resolved - might be a valid final URL or resolution failed
                    skipped += 1
                    if i <= 5:  # Show first few for debugging
                        print(f"   ⚠️  No redirect for: {original_url[:60]}")
                    continue

                # Migrate the Resource - update URL property directly
                # First check if Resource with final URL already exists
                check_result = session.run(
                    "MATCH (r:Resource {url: $final_url}) RETURN r LIMIT 1",
                    final_url=final_url,
                ).single()

                if check_result:
                    # Final URL Resource exists - migrate relationships to it, then delete old
                    migrate_query = """
                    MATCH (oldResource:Resource {url: $original_url})
                    OPTIONAL MATCH (source)-[:REFERENCES]->(oldResource)
                    WITH oldResource, [s IN collect(DISTINCT source) WHERE s IS NOT NULL] as sources

                    MATCH (newResource:Resource {url: $final_url})
                    SET newResource.domain = COALESCE(newResource.domain, oldResource.domain),
                        newResource.type = COALESCE(newResource.type, oldResource.type),
                        newResource.title = COALESCE(newResource.title, oldResource.title)

                    WITH newResource, sources, oldResource
                    UNWIND sources as source
                    MERGE (source)-[:REFERENCES]->(newResource)

                    WITH DISTINCT oldResource
                    DETACH DELETE oldResource
                    RETURN 1 as migrated
                    """
                else:
                    # Final URL Resource doesn't exist - just update the URL property
                    migrate_query = """
                    MATCH (resource:Resource {url: $original_url})
                    SET resource.url = $final_url
                    RETURN 1 as migrated
                    """

                result = session.run(
                    migrate_query, original_url=original_url, final_url=final_url
                )
                record = result.single()

                if record and record.get("migrated", 0) > 0:
                    migrated += 1
                    if (i - 1) % 10 != 0:  # Don't print if we just printed progress
                        print(f"   ✅ {original_url[:60]} → {final_url[:60]}")
                else:
                    failed += 1
                    print(f"   ⚠️  Failed to migrate: {original_url[:60]}")

            except Exception as e:
                failed += 1
                error_msg = str(e)
                # Extract more details if it's a Neo4j error
                if hasattr(e, "message"):
                    error_msg = e.message
                elif hasattr(e, "__class__"):
                    error_msg = f"{e.__class__.__name__}: {str(e)}"
                print(f"   ❌ Error processing {original_url[:60]}: {error_msg}")
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
