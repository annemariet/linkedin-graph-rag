#!/usr/bin/env python3
"""
Migrate existing Comment nodes with incorrect URN format to correct format.

Fixes Comment nodes that have simple URN format (urn:li:comment:123) to the
correct format (urn:li:comment:(parent_type:parent_id,comment_id)).

This script:
1. Finds Comment nodes with incorrect URN format
2. Finds their parent Post/Comment via COMMENTS_ON relationship
3. Reconstructs correct URN from parent URN and comment_id
4. Updates Comment node URN and URL
5. Updates all relationships that reference the old URN
"""

import os
from typing import Dict, List

from dotenv import load_dotenv
from neo4j import GraphDatabase

from linkedin_api.utils.urns import (
    build_comment_urn,
    comment_urn_to_post_url,
    parse_comment_urn,
)

load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI") or "neo4j://localhost:7687"
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME") or "neo4j"
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD") or "password"
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE") or "neo4j"


def find_comments_with_incorrect_urns(driver) -> List[Dict]:
    """
    Find Comment nodes with incorrect URN format (simple format without parent info).

    Returns:
        List of dicts with 'old_urn', 'comment_id', 'parent_urn', 'parent_type'
    """
    query = """
    MATCH (comment:Comment)
    WHERE comment.urn STARTS WITH 'urn:li:comment:'
      AND NOT comment.urn CONTAINS '('
    OPTIONAL MATCH (comment)-[:COMMENTS_ON]->(parent)
    RETURN comment.urn as old_urn,
           comment.comment_id as comment_id,
           parent.urn as parent_urn,
           labels(parent) as parent_labels
    """

    with driver.session(database=NEO4J_DATABASE) as session:
        result = session.run(query)
        comments = []
        for record in result:
            old_urn = record["old_urn"]
            comment_id = record["comment_id"]
            parent_urn = record["parent_urn"]
            parent_labels = record["parent_labels"] or []

            if parent_urn:
                if "Comment" in parent_labels:
                    # Parent is a comment - extract from its URN
                    parsed = parse_comment_urn(parent_urn)
                    if parsed and parsed.get("parent_urn"):
                        parent_urn = parsed["parent_urn"]

            if not comment_id:
                # Try to extract from old_urn
                if ":" in old_urn:
                    comment_id = old_urn.split(":")[-1]

            if comment_id and parent_urn:
                comments.append(
                    {
                        "old_urn": old_urn,
                        "comment_id": comment_id,
                        "parent_urn": parent_urn,
                    }
                )

        return comments


def migrate_comment_urn(driver, old_urn: str, new_urn: str, comment_url: str) -> bool:
    """
    Migrate a Comment node from old URN to new URN.

    Updates:
    - Comment node URN
    - Comment node URL
    - All relationships that reference the old URN

    Args:
        driver: Neo4j driver
        old_urn: The old (incorrect) URN
        new_urn: The new (correct) URN
        comment_url: The comment URL (parent post URL)

    Returns:
        True if migration succeeded, False otherwise
    """
    with driver.session(database=NEO4J_DATABASE) as session:
        # Check if new URN already exists
        check_query = "MATCH (c:Comment {urn: $new_urn}) RETURN count(c) as count"
        result = session.run(check_query, new_urn=new_urn)
        existing_count = result.single()["count"]

        if existing_count > 0:
            print(f"   ⚠️  New URN already exists, merging properties...")
            # Merge properties from old to new
            merge_query = """
            MATCH (old:Comment {urn: $old_urn})
            MATCH (new:Comment {urn: $new_urn})
            SET new += properties(old)
            SET new.urn = $new_urn
            SET new.url = $comment_url
            CALL {
                WITH old, new
                // Migrate outgoing relationships (Comment -> Post/Comment)
                MATCH (old)-[r:COMMENTS_ON]->(end)
                MERGE (new)-[r2:COMMENTS_ON]->(end)
                SET r2 = properties(r)
                DELETE r
                RETURN count(*) as outgoing_migrated
            }
            CALL {
                WITH old, new
                // Migrate incoming relationships (Person -> Comment)
                MATCH (start)-[r:CREATES]->(old)
                MERGE (start)-[r2:CREATES]->(new)
                SET r2 = properties(r)
                DELETE r
                RETURN count(*) as creates_migrated
            }
            CALL {
                WITH old, new
                // Migrate reactions targeting the comment (Person -> Comment)
                MATCH (start)-[r:REACTS_TO]->(old)
                MERGE (start)-[r2:REACTS_TO]->(new)
                SET r2 = properties(r)
                DELETE r
                RETURN count(*) as reacts_migrated
            }
            WITH old
            DETACH DELETE old
            RETURN 1 as merged
            """
            result = session.run(
                merge_query, old_urn=old_urn, new_urn=new_urn, comment_url=comment_url
            )
            return result.single() is not None

        # Step 1: Update the node URN and URL
        update_query = """
        MATCH (comment:Comment {urn: $old_urn})
        SET comment.urn = $new_urn,
            comment.url = $comment_url
        RETURN comment.urn as urn
        """
        result = session.run(
            update_query, old_urn=old_urn, new_urn=new_urn, comment_url=comment_url
        )
        if not result.single():
            return False

        # Step 2: Update relationships (they should automatically reference the updated node)
        # Neo4j relationships are stored by node identity, not URN, so they should
        # automatically point to the updated node. But let's verify by checking relationship counts.
        return True


def migrate_all_comments(driver, dry_run: bool = False):
    """
    Migrate all Comment nodes with incorrect URNs.

    Args:
        driver: Neo4j driver
        dry_run: If True, only report what would be migrated without making changes
    """
    print("🔍 Checking reaction coverage for migration context...")
    reaction_counts_query = """
    MATCH ()-[r:REACTS_TO]->(target)
    RETURN
        count(r) AS total_reactions,
        count(CASE WHEN target:Post THEN 1 END) AS reactions_to_posts,
        count(CASE WHEN target:Comment THEN 1 END) AS reactions_to_comments,
        count(CASE WHEN NOT target:Post AND NOT target:Comment THEN 1 END) AS reactions_to_other
    """
    with driver.session(database=NEO4J_DATABASE) as session:
        counts = session.run(reaction_counts_query).single()
        if counts:
            print(
                "   ✅ Reactions in graph: "
                f"{counts['total_reactions']} total "
                f"({counts['reactions_to_posts']} posts, "
                f"{counts['reactions_to_comments']} comments, "
                f"{counts['reactions_to_other']} other)"
            )

    print("\n🔍 Finding Comment nodes with incorrect URN format...")
    comments = find_comments_with_incorrect_urns(driver)
    print(f"✅ Found {len(comments)} comments to migrate\n")

    if not comments:
        print("✅ No comments need migration!")
        return

    if dry_run:
        print("🔍 DRY RUN - No changes will be made\n")
        for comment in comments:
            new_urn = build_comment_urn(comment["parent_urn"], comment["comment_id"])
            comment_url = comment_urn_to_post_url(new_urn) or ""
            print(f"   Would migrate:")
            print(f"     Old URN: {comment['old_urn']}")
            print(f"     New URN: {new_urn}")
            print(f"     URL: {comment_url}")
            print()
        return

    success_count = 0
    failed_count = 0

    for i, comment in enumerate(comments, 1):
        print(f"[{i}/{len(comments)}] Migrating: {comment['old_urn']}")

        new_urn = build_comment_urn(comment["parent_urn"], comment["comment_id"])
        if not new_urn:
            print(f"   ❌ Failed to build new URN")
            failed_count += 1
            continue

        comment_url = comment_urn_to_post_url(new_urn) or ""
        print(f"   New URN: {new_urn}")
        print(f"   URL: {comment_url}")

        if migrate_comment_urn(driver, comment["old_urn"], new_urn, comment_url):
            print(f"   ✅ Migrated successfully")
            success_count += 1
        else:
            print(f"   ❌ Migration failed")
            failed_count += 1

        print()

    print("=" * 60)
    print("📊 MIGRATION SUMMARY")
    print("=" * 60)
    print(f"Total comments found: {len(comments)}")
    print(f"Successfully migrated: {success_count}")
    print(f"Failed: {failed_count}")
    print()


def main():
    """Main function to migrate comment URNs."""
    import sys

    dry_run = "--dry-run" in sys.argv

    print("🔄 LinkedIn Comment URN Migration")
    print("=" * 60)

    if dry_run:
        print("⚠️  DRY RUN MODE - No changes will be made\n")

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

    # Migrate comments
    migrate_all_comments(driver, dry_run=dry_run)

    driver.close()


if __name__ == "__main__":
    main()
