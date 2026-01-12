#!/usr/bin/env python3
"""
Build Neo4j graph from extracted LinkedIn data.

This is Step 2 of the graph building workflow:
1. extract_graph_data.py → Fetch and extract data to JSON
2. build_graph.py → Load JSON into Neo4j and enrich

Loads nodes and relationships from JSON file, then enriches:
- Post nodes with author information (name, profile URL)
- Post/Comment nodes with external resources (articles, videos, repos)

Incremental Loading:
- By default, only loads nodes/relationships that don't already exist (incremental mode)
- Uses MERGE to avoid duplicates and preserve existing data (e.g., author info, chunks)
- Use --full-rebuild to delete all data and recreate from scratch
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


def create_nodes_batch(tx, nodes_batch, incremental=True):
    """
    Create or merge nodes with dynamic labels and properties using standard Cypher.

    Args:
        tx: Neo4j transaction
        nodes_batch: List of node dictionaries
        incremental: If True, use MERGE for nodes with urn property to avoid duplicates.
                    If False, use CREATE (only for full rebuilds).
    """
    created = 0
    for node in nodes_batch:
        labels_str = ":".join(node["labels"])
        props = node["properties"]

        if incremental and "urn" in props:
            # Use MERGE on URN to avoid duplicates, preserve existing properties like author info
            query = f"""
            MERGE (n:{labels_str} {{urn: $urn}})
            ON CREATE SET n = $props
            ON MATCH SET n += $props
            RETURN n
            """
            tx.run(query, urn=props["urn"], props=props)
        else:
            # Use CREATE for fresh inserts (only when incremental=False)
            query = f"CREATE (n:{labels_str}) SET n = $props RETURN n"
            tx.run(query, props=props)
        created += 1
    return created


def create_relationships_batch(tx, rels_batch, incremental=True):
    """
    Create or merge relationships with dynamic type and properties using standard Cypher.

    Args:
        tx: Neo4j transaction
        rels_batch: List of relationship dictionaries
        incremental: If True, use MERGE to avoid duplicate relationships.
                    If False, use CREATE (only for full rebuilds).
    """
    created = 0
    for rel in rels_batch:
        rel_type = rel["type"]

        if incremental:
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


def get_existing_node_urns(driver):
    """Get set of all existing node URNs in the graph."""
    query = "MATCH (n) WHERE n.urn IS NOT NULL RETURN n.urn as urn"
    with driver.session(database=NEO4J_DATABASE) as session:
        result = session.run(query)
        return {record["urn"] for record in result}


def get_existing_relationships(driver):
    """Get set of all existing relationships as (start_urn, rel_type, end_urn) tuples."""
    query = """
    MATCH (start)-[r]->(end)
    WHERE start.urn IS NOT NULL AND end.urn IS NOT NULL
    RETURN start.urn as start_urn, type(r) as rel_type, end.urn as end_urn
    """
    with driver.session(database=NEO4J_DATABASE) as session:
        result = session.run(query)
        return {
            (record["start_urn"], record["rel_type"], record["end_urn"])
            for record in result
        }


def filter_new_nodes(nodes, existing_urns):
    """Filter out nodes that already exist in the graph."""
    new_nodes = []
    for node in nodes:
        urn = node.get("properties", {}).get("urn")
        if not urn or urn not in existing_urns:
            new_nodes.append(node)
    return new_nodes


def filter_new_relationships(relationships, existing_rels):
    """Filter out relationships that already exist in the graph."""
    new_rels = []
    for rel in relationships:
        key = (rel["startNode"], rel["type"], rel["endNode"])
        if key not in existing_rels:
            new_rels.append(rel)
    return new_rels


def load_graph_data(driver, json_file, incremental=True):
    """
    Load nodes and relationships from JSON into Neo4j.

    Args:
        driver: Neo4j driver
        json_file: Path to JSON file with nodes and relationships
        incremental: If True, only load nodes/relationships that don't already exist.
                    Uses MERGE to avoid duplicates. If False, loads everything using CREATE.
    """
    with open(json_file, "r") as f:
        data = json.load(f)

    nodes = data.get("nodes", [])
    relationships = data.get("relationships", [])

    print(
        f"📊 JSON file contains {len(nodes)} nodes and {len(relationships)} relationships"
    )

    # Filter out existing nodes/relationships if incremental mode
    if incremental:
        print("🔍 Checking for existing nodes and relationships...")
        existing_urns = get_existing_node_urns(driver)
        existing_rels = get_existing_relationships(driver)

        print(
            f"   Found {len(existing_urns)} existing nodes and "
            f"{len(existing_rels)} existing relationships"
        )

        nodes = filter_new_nodes(nodes, existing_urns)
        relationships = filter_new_relationships(relationships, existing_rels)

        print(
            f"✅ Filtered to {len(nodes)} new nodes and "
            f"{len(relationships)} new relationships to load"
        )

        if len(nodes) == 0 and len(relationships) == 0:
            print("✅ No new data to load - graph is up to date!")
            return
    else:
        print(
            "⚠️  Full rebuild mode - will create all nodes/relationships "
            "(may fail if duplicates exist)"
        )

    # Create nodes in batches
    with driver.session(database=NEO4J_DATABASE) as session:
        for i in range(0, len(nodes), BATCH_SIZE):
            batch = nodes[i : i + BATCH_SIZE]
            count = session.execute_write(create_nodes_batch, batch, incremental)
            action = "Merged" if incremental else "Created"
            batch_num = i // BATCH_SIZE + 1
            print(f"{action} {count} nodes (batch {batch_num})")

    # Create relationships in batches
    with driver.session(database=NEO4J_DATABASE) as session:
        for i in range(0, len(relationships), BATCH_SIZE):
            batch = relationships[i : i + BATCH_SIZE]
            count = session.execute_write(
                create_relationships_batch, batch, incremental
            )
            action = "Merged" if incremental else "Created"
            batch_num = i // BATCH_SIZE + 1
            print(f"{action} {count} relationships (batch {batch_num})")

    print("✅ Graph built successfully!")


if __name__ == "__main__":
    import sys
    import glob
    from pathlib import Path

    # Parse arguments
    full_rebuild = "--full-rebuild" in sys.argv

    if full_rebuild:
        sys.argv.remove("--full-rebuild")

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

    # Determine loading mode
    if full_rebuild:
        print("⚠️  Full rebuild mode - will delete all data and recreate\n")
        db_cleanup(driver)
        incremental = False
    else:
        print(
            "✅ Incremental loading enabled by default (use --full-rebuild to disable)\n"
        )
        incremental = True

    load_graph_data(driver, json_file, incremental=incremental)

    # Enrich posts with author information (only for posts without author info)
    enrich_posts_with_authors(driver)

    # Extract and link external resources from posts
    enrich_posts_with_resources(driver, json_file=json_file, database=NEO4J_DATABASE)

    driver.close()
