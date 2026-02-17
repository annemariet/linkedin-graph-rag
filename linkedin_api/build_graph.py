#!/usr/bin/env python3
"""
Build Neo4j graph from extracted LinkedIn data.

This is Step 2 of the graph building workflow:
1. extract_graph_data.py -> Fetch and extract data to CSV (+ legacy JSON)
2. build_graph.py -> Load CSV/JSON into Neo4j (Phase A: structural graph)

Supports two input modes:
- CSV (default): Reads master CSV at ~/.linkedin_api/data/activities.csv
- JSON (legacy): Reads neo4j_data_*.json from outputs/ via --json-file

Incremental Loading:
- By default, only loads nodes/relationships that don't already exist
- Uses MERGE to avoid duplicates and preserve existing data
- Use --full-rebuild to delete all data and recreate from scratch

Enrichment (author info, resources, LLM extraction) is handled separately
by enrich_graph.py (Phase B).
"""

import json

import dotenv
from os import getenv
from typing import List

from neo4j import GraphDatabase

from linkedin_api.activity_csv import (
    ActivityRecord,
    ActivityType,
    get_default_csv_path,
    load_records_csv,
)
from linkedin_api.graph_schema import PHASE_A_RELATIONSHIP_TYPES
from linkedin_api.utils.urns import (
    extract_urn_id,
    urn_to_post_url,
    comment_urn_to_post_url,
    parse_comment_urn,
)


dotenv.load_dotenv()

BATCH_SIZE = 500


def get_neo4j_config():
    """Return Neo4j connection config from environment."""
    return {
        "url": getenv("NEO4J_URI") or "neo4j://localhost:7687",
        "username": getenv("NEO4J_USERNAME") or "neo4j",
        "password": getenv("NEO4J_PASSWORD") or "neoneoneo",
        "database": getenv("NEO4J_DATABASE") or "neo4j",
    }


def create_driver(config=None):
    """Create and verify a Neo4j driver."""
    if config is None:
        config = get_neo4j_config()
    drv = GraphDatabase.driver(
        config["url"], auth=(config["username"], config["password"])
    )
    drv.verify_connectivity()
    return drv


def db_cleanup(driver, database="neo4j"):
    print("Doing Database Cleanup.")
    query = "MATCH (n) DETACH DELETE (n)"
    with driver.session(database=database) as session:
        session.run(query)
        print("Database Cleanup Done. Using blank database.")


# -- Node/relationship batch helpers (shared by CSV and JSON loaders) ------


def create_nodes_batch(tx, nodes_batch, incremental=True):
    """
    Create or merge nodes with dynamic labels and properties using standard Cypher.

    Args:
        tx: Neo4j transaction
        nodes_batch: List of node dictionaries with 'labels' and 'properties'
        incremental: If True, use MERGE on urn to avoid duplicates.
    """
    created = 0
    for node in nodes_batch:
        labels_str = ":".join(node["labels"])
        props = node["properties"]

        if incremental and "urn" in props:
            query = f"""
            MERGE (n:{labels_str} {{urn: $urn}})
            ON CREATE SET n = $props
            ON MATCH SET n += $props
            RETURN n
            """
            tx.run(query, urn=props["urn"], props=props)
        else:
            query = f"CREATE (n:{labels_str}) SET n = $props RETURN n"
            tx.run(query, props=props)
        created += 1
    return created


def create_relationships_batch(tx, rels_batch, incremental=True):
    """
    Create or merge relationships with dynamic type and properties.

    Args:
        tx: Neo4j transaction
        rels_batch: List of relationship dictionaries
        incremental: If True, use MERGE to avoid duplicate relationships.
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


def _load_batched(driver, database, nodes, relationships, incremental=True):
    """Load nodes and relationships into Neo4j in batches."""
    with driver.session(database=database) as session:
        for i in range(0, len(nodes), BATCH_SIZE):
            batch = nodes[i : i + BATCH_SIZE]
            count = session.execute_write(create_nodes_batch, batch, incremental)
            action = "Merged" if incremental else "Created"
            batch_num = i // BATCH_SIZE + 1
            print(f"{action} {count} nodes (batch {batch_num})")

    with driver.session(database=database) as session:
        for i in range(0, len(relationships), BATCH_SIZE):
            batch = relationships[i : i + BATCH_SIZE]
            count = session.execute_write(
                create_relationships_batch, batch, incremental
            )
            action = "Merged" if incremental else "Created"
            batch_num = i // BATCH_SIZE + 1
            print(f"{action} {count} relationships (batch {batch_num})")


# -- Incremental filtering -------------------------------------------------


def get_existing_node_urns(driver, database="neo4j"):
    """Get set of all existing node URNs in the graph."""
    query = "MATCH (n) WHERE n.urn IS NOT NULL RETURN n.urn as urn"
    with driver.session(database=database) as session:
        result = session.run(query)
        return {record["urn"] for record in result}


def get_existing_relationships(driver, database="neo4j"):
    """Get set of all existing relationships as (start_urn, rel_type, end_urn) tuples."""
    query = """
    MATCH (start)-[r]->(end)
    WHERE start.urn IS NOT NULL AND end.urn IS NOT NULL
    RETURN start.urn as start_urn, type(r) as rel_type, end.urn as end_urn
    """
    with driver.session(database=database) as session:
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


# -- CSV loading (Phase A) ------------------------------------------------


def _records_to_nodes_and_rels(
    records: List[ActivityRecord],
) -> tuple[list[dict], list[dict]]:
    """Convert ActivityRecords to node/relationship dicts for Neo4j loading.

    Uses new relationship names: IS_AUTHOR_OF, REACTED_TO, COMMENTS_ON, REPOSTS.
    """
    people: dict = {}
    posts: dict = {}
    comments: dict = {}
    relationships: list[dict] = []

    for rec in records:
        # Person node
        if rec.author_urn and rec.author_urn.startswith("urn:li:person:"):
            if rec.author_urn not in people:
                people[rec.author_urn] = {
                    "labels": ["Person"],
                    "properties": {
                        "urn": rec.author_urn,
                        "person_id": extract_urn_id(rec.author_urn) or "",
                    },
                }

        timestamp = int(rec.time) if rec.time else None

        if rec.activity_type == ActivityType.POST.value:
            post_urn = rec.activity_urn
            props: dict = {
                "urn": post_urn,
                "post_id": extract_urn_id(post_urn) or "",
                "url": rec.post_url,
                "type": "original",
                "has_content": bool(rec.content),
                "timestamp": timestamp,
                "created_at": rec.created_at,
            }
            if rec.content:
                props["content"] = rec.content
            posts.setdefault(post_urn, {"labels": ["Post"], "properties": props})
            relationships.append(
                {
                    "type": "IS_AUTHOR_OF",
                    "startNode": rec.author_urn,
                    "endNode": post_urn,
                    "properties": {
                        "timestamp": timestamp,
                        "created_at": rec.created_at,
                    },
                }
            )

        elif rec.activity_type == ActivityType.REPOST.value:
            post_urn = rec.activity_urn
            props = {
                "urn": post_urn,
                "post_id": extract_urn_id(post_urn) or "",
                "url": rec.post_url,
                "type": "repost",
                "has_content": bool(rec.content),
                "timestamp": timestamp,
                "created_at": rec.created_at,
            }
            if rec.content:
                props["content"] = rec.content
            if rec.original_post_urn:
                props["original_post_urn"] = rec.original_post_urn
            posts.setdefault(post_urn, {"labels": ["Post"], "properties": props})
            relationships.append(
                {
                    "type": "REPOSTS",
                    "startNode": rec.author_urn,
                    "endNode": post_urn,
                    "properties": {
                        "timestamp": timestamp,
                        "created_at": rec.created_at,
                    },
                }
            )
            if rec.original_post_urn:
                orig_urn = rec.original_post_urn
                if orig_urn not in posts:
                    posts[orig_urn] = {
                        "labels": ["Post"],
                        "properties": {
                            "urn": orig_urn,
                            "post_id": extract_urn_id(orig_urn) or "",
                            "url": urn_to_post_url(orig_urn) or "",
                        },
                    }
                relationships.append(
                    {
                        "type": "REPOSTS",
                        "startNode": post_urn,
                        "endNode": orig_urn,
                        "properties": {"relationship_type": "repost_of"},
                    }
                )

        elif rec.activity_type in (
            ActivityType.REACTION_TO_POST.value,
            ActivityType.REACTION_TO_COMMENT.value,
        ):
            target_urn = rec.activity_urn
            if target_urn not in posts and target_urn not in comments:
                if target_urn.startswith("urn:li:comment:"):
                    comments[target_urn] = {
                        "labels": ["Comment"],
                        "properties": {"urn": target_urn},
                    }
                else:
                    posts[target_urn] = {
                        "labels": ["Post"],
                        "properties": {
                            "urn": target_urn,
                            "post_id": extract_urn_id(target_urn) or "",
                            "url": urn_to_post_url(target_urn) or "",
                        },
                    }
            relationships.append(
                {
                    "type": "REACTED_TO",
                    "startNode": rec.author_urn,
                    "endNode": target_urn,
                    "properties": {
                        "reaction_type": rec.reaction_type,
                        "timestamp": timestamp,
                        "created_at": rec.created_at,
                    },
                }
            )

        elif rec.activity_type == ActivityType.COMMENT.value:
            comment_urn = rec.activity_urn
            parsed = parse_comment_urn(comment_urn)
            comment_id = parsed.get("comment_id") if parsed else ""
            comment_url = comment_urn_to_post_url(comment_urn) or ""
            c_props: dict = {
                "urn": comment_urn,
                "comment_id": comment_id or "",
                "text": rec.content,
                "timestamp": timestamp,
                "created_at": rec.created_at,
                "url": comment_url,
            }
            comments.setdefault(
                comment_urn, {"labels": ["Comment"], "properties": c_props}
            )
            # Ensure parent post node exists
            post_urn = ""
            if parsed and parsed.get("parent_urn"):
                post_urn = parsed["parent_urn"]
            if post_urn and post_urn not in posts:
                posts[post_urn] = {
                    "labels": ["Post"],
                    "properties": {
                        "urn": post_urn,
                        "post_id": extract_urn_id(post_urn) or "",
                        "url": urn_to_post_url(post_urn) or "",
                    },
                }
            relationships.append(
                {
                    "type": "IS_AUTHOR_OF",
                    "startNode": rec.author_urn,
                    "endNode": comment_urn,
                    "properties": {
                        "timestamp": timestamp,
                        "created_at": rec.created_at,
                    },
                }
            )
            target_urn = rec.parent_urn or post_urn
            if target_urn:
                relationships.append(
                    {
                        "type": "COMMENTS_ON",
                        "startNode": comment_urn,
                        "endNode": target_urn,
                        "properties": {
                            "timestamp": timestamp,
                            "created_at": rec.created_at,
                        },
                    }
                )

        elif rec.activity_type == ActivityType.INSTANT_REPOST.value:
            target_urn = rec.activity_urn
            if target_urn not in posts:
                posts[target_urn] = {
                    "labels": ["Post"],
                    "properties": {
                        "urn": target_urn,
                        "post_id": extract_urn_id(target_urn) or "",
                        "url": urn_to_post_url(target_urn) or "",
                    },
                }
            relationships.append(
                {
                    "type": "REPOSTS",
                    "startNode": rec.author_urn,
                    "endNode": target_urn,
                    "properties": {
                        "timestamp": timestamp,
                        "created_at": rec.created_at,
                        "repost_type": "instant",
                    },
                }
            )

    # Validate relationship types
    for rel in relationships:
        if rel["type"] not in PHASE_A_RELATIONSHIP_TYPES:
            raise ValueError(
                f"Unexpected relationship type {rel['type']!r} "
                f"(allowed: {PHASE_A_RELATIONSHIP_TYPES})"
            )

    nodes = list(people.values()) + list(posts.values()) + list(comments.values())
    return nodes, relationships


def load_from_csv(driver, csv_path=None, incremental=True, database=None):
    """Load graph from master CSV (Phase A: structural graph).

    Args:
        driver: Neo4j driver
        csv_path: Path to CSV file (default: master CSV)
        incremental: If True, MERGE to avoid duplicates
        database: Neo4j database name
    """
    if database is None:
        database = get_neo4j_config()["database"]
    if csv_path is None:
        csv_path = get_default_csv_path()

    records = load_records_csv(csv_path)
    if not records:
        print(f"No records found in {csv_path}")
        return

    print(f"📊 CSV contains {len(records)} activity records")

    nodes, relationships = _records_to_nodes_and_rels(records)
    print(f"   -> {len(nodes)} nodes, {len(relationships)} relationships")

    if incremental:
        print("🔍 Checking for existing nodes and relationships...")
        existing_urns = get_existing_node_urns(driver, database)
        existing_rels = get_existing_relationships(driver, database)
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
        if not nodes and not relationships:
            print("✅ No new data to load - graph is up to date!")
            return

    _load_batched(driver, database, nodes, relationships, incremental)
    print("✅ Graph built successfully!")


# -- JSON loading (legacy backward compat) ---------------------------------


def load_graph_data(driver, json_file, incremental=True, database=None):
    """
    Load nodes and relationships from JSON into Neo4j (legacy).

    Args:
        driver: Neo4j driver
        json_file: Path to JSON file with nodes and relationships
        incremental: If True, only load new nodes/relationships.
        database: Neo4j database name
    """
    if database is None:
        database = get_neo4j_config()["database"]

    with open(json_file, "r") as f:
        data = json.load(f)

    nodes = data.get("nodes", [])
    relationships = data.get("relationships", [])

    print(
        f"📊 JSON file contains {len(nodes)} nodes and "
        f"{len(relationships)} relationships"
    )

    if incremental:
        print("🔍 Checking for existing nodes and relationships...")
        existing_urns = get_existing_node_urns(driver, database)
        existing_rels = get_existing_relationships(driver, database)
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
        if not nodes and not relationships:
            print("✅ No new data to load - graph is up to date!")
            return
    else:
        print(
            "⚠️  Full rebuild mode - will create all nodes/relationships "
            "(may fail if duplicates exist)"
        )

    _load_batched(driver, database, nodes, relationships, incremental)
    print("✅ Graph built successfully!")


if __name__ == "__main__":
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Build Neo4j graph from LinkedIn data")
    parser.add_argument(
        "--json-file",
        help="Legacy JSON file to load (default: use master CSV)",
    )
    parser.add_argument(
        "--full-rebuild",
        action="store_true",
        help="Delete all data and recreate from scratch",
    )
    parser.add_argument(
        "--csv",
        help="Path to CSV file (default: master CSV at ~/.linkedin_api/data/)",
    )
    args = parser.parse_args()

    config = get_neo4j_config()
    driver = create_driver(config)

    incremental = not args.full_rebuild
    if args.full_rebuild:
        print("⚠️  Full rebuild mode - will delete all data and recreate\n")
        db_cleanup(driver, config["database"])
    else:
        print(
            "✅ Incremental loading enabled by default "
            "(use --full-rebuild to disable)\n"
        )

    if args.json_file:
        # Legacy JSON mode
        print(f"📂 Loading from JSON: {args.json_file}")
        load_graph_data(
            driver, args.json_file, incremental=incremental, database=config["database"]
        )
    else:
        # CSV mode (default)
        csv_path = Path(args.csv) if args.csv else None
        if csv_path:
            print(f"📂 Loading from CSV: {csv_path}")
        else:
            print(f"📂 Loading from master CSV: {get_default_csv_path()}")
        load_from_csv(
            driver,
            csv_path=csv_path,
            incremental=incremental,
            database=config["database"],
        )

    driver.close()
