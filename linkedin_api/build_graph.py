#!/usr/bin/env python3
"""
Build Neo4j graph from extracted LinkedIn data.

This is Step 2 of the graph building workflow:
1. extract_graph_data.py → Fetch and extract data to JSON
2. build_graph.py → Load JSON into Neo4j and enrich

Loads nodes and relationships from JSON file, then enriches:
- Post nodes with author information (name, profile URL)
- Post/Comment nodes with external resources (articles, videos, repos)
"""

import dotenv
from os import getenv
from neo4j import GraphDatabase
import json
from linkedin_api.enrich_profiles import (
    get_posts_without_author,
    extract_author_profile,
    update_post_author,
)
from linkedin_api.extract_resources import enrich_posts_with_resources


dotenv.load_dotenv()

NEO4J_URL = getenv("NEO4J_URI") or "neo4j://localhost:7687"
NEO4J_USERNAME = getenv("NEO4J_USERNAME") or "neo4j"
NEO4J_PASSWORD = getenv("NEO4J_PASSWORD") or "neoneoneo"
NEO4J_DATABASE = getenv("NEO4J_DATABASE") or "neo4j"
BATCH_SIZE = 500


driver = GraphDatabase.driver(NEO4J_URL, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))

driver.verify_connectivity()  # Throws an error if the connection is not successful


def db_cleanup(driver):
    print("Doing Database Cleanup.")
    query = "MATCH (n) DETACH DELETE (n)"
    with driver.session() as session:
        session.run(query)
        print("Database Cleanup Done. Using blank database.")


def create_nodes_batch(tx, nodes_batch, use_merge=False):
    """Create or merge nodes with dynamic labels and properties using standard Cypher."""
    created = 0
    for node in nodes_batch:
        labels_str = ":".join(node["labels"])
        props = node["properties"]

        if use_merge and "urn" in props:
            # Use MERGE on URN to avoid duplicates, preserve existing properties like author info
            query = f"""
            MERGE (n:{labels_str} {{urn: $urn}})
            ON CREATE SET n = $props
            ON MATCH SET n += $props
            RETURN n
            """
            tx.run(query, urn=props["urn"], props=props)
        else:
            # Use CREATE for fresh inserts
            query = f"CREATE (n:{labels_str}) SET n = $props RETURN n"
            tx.run(query, props=props)
        created += 1
    return created


def create_relationships_batch(tx, rels_batch, use_merge=False):
    """Create or merge relationships with dynamic type and properties using standard Cypher."""
    created = 0
    for rel in rels_batch:
        rel_type = rel["type"]

        if use_merge:
            query = f"""
            MATCH (start {{urn: $startNode}})
            MATCH (end {{urn: $endNode}})
            MERGE (start)-[r:{rel_type}]->(end)
            ON CREATE SET r = $props
            RETURN r
            """
        else:
            query = f"""
            MATCH (start {{urn: $startNode}})
            MATCH (end {{urn: $endNode}})
            CREATE (start)-[r:{rel_type}]->(end)
            SET r = $props
            RETURN r
            """

        result = tx.run(
            query,
            startNode=rel["startNode"],
            endNode=rel["endNode"],
            props=rel["properties"],
        )
        if result.single():
            created += 1
    return created


def enrich_posts_with_authors(driver):
    """
    Enrich Post nodes with author information by scraping LinkedIn URLs.
    Only processes posts that don't already have author information.
    """
    print("\n🔍 Enriching posts with author information...")

    posts = get_posts_without_author(driver)

    if not posts:
        print("✅ All posts already have author information!\n")
        return

    print(f"📊 Found {len(posts)} posts to enrich")

    success_count = 0
    failed_count = 0

    for i, post in enumerate(posts, 1):
        if i % 10 == 0 or i == 1:
            print(f"   Processing {i}/{len(posts)}...")

        author_info = extract_author_profile(post["url"])

        if author_info and update_post_author(driver, post["urn"], author_info):
            success_count += 1
        else:
            failed_count += 1

    print(f"✅ Enriched {success_count} posts with author information")
    if failed_count > 0:
        print(f"⚠️  Failed to enrich {failed_count} posts")
    print()


def load_graph_data(driver, json_file, use_merge=False):
    """Load nodes and relationships from JSON into Neo4j."""
    with open(json_file, "r") as f:
        data = json.load(f)

    nodes = data.get("nodes", [])
    relationships = data.get("relationships", [])

    print(f"Loading {len(nodes)} nodes and {len(relationships)} relationships...")
    if use_merge:
        print("Using MERGE to preserve existing data (e.g., author information)")

    # Create nodes in batches
    with driver.session() as session:
        for i in range(0, len(nodes), BATCH_SIZE):
            batch = nodes[i : i + BATCH_SIZE]
            count = session.execute_write(create_nodes_batch, batch, use_merge)
            print(
                f"{'Merged' if use_merge else 'Created'} {count} nodes (batch {i // BATCH_SIZE + 1})"
            )

    # Create relationships in batches
    with driver.session() as session:
        for i in range(0, len(relationships), BATCH_SIZE):
            batch = relationships[i : i + BATCH_SIZE]
            count = session.execute_write(create_relationships_batch, batch, use_merge)
            print(
                f"{'Merged' if use_merge else 'Created'} {count} relationships (batch {i // BATCH_SIZE + 1})"
            )

    print("Graph built successfully!")


if __name__ == "__main__":
    import sys
    import glob
    from pathlib import Path

    # Parse arguments
    skip_cleanup = "--skip-cleanup" in sys.argv
    if skip_cleanup:
        sys.argv.remove("--skip-cleanup")

    # Get JSON filename from command line or find most recent neo4j_data file
    if len(sys.argv) > 1:
        json_file = sys.argv[1]
    else:
        # Find most recent neo4j_data_*.json file in outputs/ directory
        output_dir = Path("outputs")
        files = list(output_dir.glob("neo4j_data_*.json"))
        if files:
            json_file = str(max(files, key=lambda p: p.stat().st_mtime))
            print(f"📂 Using most recent file: {json_file}")
        else:
            # Fallback to old location or default
            old_files = glob.glob("neo4j_data_*.json")
            if old_files:
                json_file = max(old_files)
                print(f"📂 Using most recent file (old location): {json_file}")
            else:
                json_file = "outputs/neo4j_data.json"
                print(f"📂 Using default file: {json_file}")

    if skip_cleanup:
        print("⚠️  Skipping database cleanup - will merge new data with existing\n")
    else:
        db_cleanup(driver)

    load_graph_data(driver, json_file, use_merge=skip_cleanup)

    # Enrich posts with author information (only for posts without author info)
    enrich_posts_with_authors(driver)

    # Extract and link external resources from posts
    enrich_posts_with_resources(driver, json_file=json_file)

    driver.close()
