#!/usr/bin/env python3
"""
Fix existing repost CREATES/REPOSTS in Neo4j using re-extracted JSON.

After fixing extraction so repost author = actor (see LUC-24), re-run extraction
to produce new neo4j_data_*.json. This script reads that JSON and updates the
graph: for each repost share (Post with original_post_urn), removes wrong
CREATES/REPOSTS from the original author and ensures REPOSTS from the correct
reposter (from the JSON).

Usage:
  uv run python -m linkedin_api.fix_repost_authors [path_to_neo4j_data.json]
  uv run python -m linkedin_api.fix_repost_authors  # uses latest in outputs/

Options:
  --dry-run  Report what would be changed without writing.
"""

import argparse
import json
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI") or "neo4j://localhost:7687"
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME") or "neo4j"
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD") or "password"
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE") or "neo4j"


def load_extraction_json(path: Path) -> dict:
    """Load neo4j_data JSON (nodes have id, labels, properties; rels have startNode, endNode, type)."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_reposter_map(data: dict) -> dict:
    """
    Build map repost_share_urn -> reposter_urn from extraction JSON.

    Repost shares are Post nodes with original_post_urn. In the fixed extraction,
    REPOSTS from person to repost_share links the reposter.
    """
    nodes = data.get("nodes", [])
    relationships = data.get("relationships", [])
    repost_shares = set()
    for node in nodes:
        labels = node.get("labels") or []
        if "Post" not in labels:
            continue
        props = node.get("properties") or {}
        if props.get("original_post_urn"):
            repost_shares.add(node.get("id"))
    person_urns = {n["id"] for n in nodes if "Person" in (n.get("labels") or [])}
    reposter_map = {}
    for rel in relationships:
        if rel.get("type") != "REPOSTS":
            continue
        start = rel.get("startNode")
        end = rel.get("endNode")
        if start in person_urns and end in repost_shares:
            reposter_map[end] = start
    return reposter_map


def get_repost_shares_in_db(driver) -> list:
    """Return list of (post_urn,) for Post nodes that have original_post_urn."""
    query = """
    MATCH (post:Post)
    WHERE post.original_post_urn IS NOT NULL AND post.urn IS NOT NULL
    RETURN post.urn as urn
    """
    with driver.session(database=NEO4J_DATABASE) as session:
        result = session.run(query)
        return [record["urn"] for record in result]


def get_current_author_of_post(driver, post_urn: str) -> Optional[str]:
    """Return the URN of the Person that has CREATES or REPOSTS to this post, or None."""
    query = """
    MATCH (p:Person)-[r:CREATES|REPOSTS]->(post:Post {urn: $urn})
    RETURN p.urn as person_urn
    LIMIT 1
    """
    with driver.session(database=NEO4J_DATABASE) as session:
        result = session.run(query, urn=post_urn)
        record = result.single()
        return record["person_urn"] if record else None


def fix_repost_author(
    driver, post_urn: str, correct_reposter_urn: str, dry_run: bool
) -> bool:
    """
    Remove existing CREATES/REPOSTS from any Person to this post, then MERGE (reposter)-[:REPOSTS]->(post).
    """
    if dry_run:
        return True
    person_id = (
        correct_reposter_urn.split(":")[-1]
        if ":" in correct_reposter_urn
        else correct_reposter_urn
    )
    query = """
    MATCH (post:Post {urn: $post_urn})
    OPTIONAL MATCH (any_person:Person)-[r:CREATES|REPOSTS]->(post)
    WITH post, r
    DELETE r
    WITH post
    MERGE (reposter:Person {urn: $reposter_urn})
    ON CREATE SET reposter.person_id = $person_id
    MERGE (reposter)-[:REPOSTS]->(post)
    RETURN post.urn as urn
    """
    with driver.session(database=NEO4J_DATABASE) as session:
        result = session.run(
            query,
            post_urn=post_urn,
            reposter_urn=correct_reposter_urn,
            person_id=person_id,
        )
        return result.single() is not None


def main():
    parser = argparse.ArgumentParser(
        description="Fix repost authors in Neo4j from re-extracted JSON"
    )
    parser.add_argument(
        "json_path",
        nargs="?",
        help="Path to neo4j_data_*.json (default: latest in outputs/)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Only report what would be changed"
    )
    args = parser.parse_args()

    if args.json_path:
        path = Path(args.json_path)
    else:
        # Check outputs/ relative to script location and git root
        script_dir = Path(__file__).resolve().parent.parent
        candidates = [script_dir / "outputs"]
        # Try to find git root and check outputs/ there
        try:
            import subprocess

            git_root = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=script_dir,
                capture_output=True,
                text=True,
                check=False,
            )
            if git_root.returncode == 0:
                git_outputs = Path(git_root.stdout.strip()) / "outputs"
                if git_outputs not in candidates:
                    candidates.append(git_outputs)
        except Exception:
            pass
        files = []
        checked = []
        for candidate in candidates:
            if candidate.exists():
                checked.append(str(candidate))
                files.extend(candidate.glob("neo4j_data_*.json"))
        if not files:
            print(
                "No neo4j_data_*.json found in outputs/. Run extract_graph_data first."
            )
            print("If running from a worktree, specify the path explicitly:")
            print(
                "  python -m linkedin_api.fix_repost_authors /path/to/neo4j_data_*.json"
            )
            if checked:
                print(f"Checked: {', '.join(checked)}")
            return 1
        path = max(files, key=lambda p: p.stat().st_mtime)
        print(f"Using latest: {path}")

    if not path.exists():
        print(f"File not found: {path}")
        return 1

    data = load_extraction_json(path)
    reposter_map = build_reposter_map(data)
    if not reposter_map:
        print("No repost shares found in JSON (or no REPOSTS from Person to them).")
        return 0

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))
    try:
        driver.verify_connectivity()
    except Exception as e:
        print(f"Neo4j connection failed: {e}")
        return 1

    repost_urns_in_db = get_repost_shares_in_db(driver)
    updated = 0
    skipped_no_mapping = 0
    skipped_already_correct = 0
    for post_urn in repost_urns_in_db:
        correct_reposter = reposter_map.get(post_urn)
        if not correct_reposter:
            skipped_no_mapping += 1
            continue
        current = get_current_author_of_post(driver, post_urn)
        if current == correct_reposter:
            skipped_already_correct += 1
            continue
        if args.dry_run:
            print(
                f"Would fix: {post_urn}  current={current}  correct={correct_reposter}"
            )
        else:
            fix_repost_author(driver, post_urn, correct_reposter, dry_run=False)
        updated += 1

    print(f"Repost shares in DB: {len(repost_urns_in_db)}")
    print(f"In JSON mapping: {len(reposter_map)}")
    if args.dry_run:
        print(f"Would update: {updated}")
    else:
        print(f"Updated: {updated}")
    print(f"Skipped (no mapping in JSON): {skipped_no_mapping}")
    print(f"Skipped (already correct): {skipped_already_correct}")
    driver.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
