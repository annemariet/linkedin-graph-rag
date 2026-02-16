#!/usr/bin/env python3
"""
Migrate Neo4j graph schema to new relationship names.

Renames:
  CREATES  -> IS_AUTHOR_OF
  REACTS_TO -> REACTED_TO
  ON_POST  -> COMMENTS_ON

Each migration: MATCH old rel, CREATE new rel with same properties, DELETE old.

Usage:
  uv run python -m linkedin_api.migrate_schema [--dry-run]
"""

import argparse

import dotenv

from linkedin_api.build_graph import create_driver, get_neo4j_config
from linkedin_api.graph_schema import RELATIONSHIP_RENAMES

dotenv.load_dotenv()


def migrate_relationship(driver, database, old_type, new_type, dry_run=False):
    """Rename a relationship type by copying properties and deleting the old one.

    Returns the number of relationships migrated.
    """
    count_query = f"""
    MATCH ()-[r:{old_type}]->()
    RETURN count(r) as cnt
    """
    with driver.session(database=database) as session:
        result = session.run(count_query)
        count = result.single()["cnt"]

    if count == 0:
        print(f"  {old_type} -> {new_type}: 0 relationships (nothing to do)")
        return 0

    if dry_run:
        print(f"  {old_type} -> {new_type}: {count} relationships (dry run)")
        return count

    migrate_query = f"""
    MATCH (a)-[r:{old_type}]->(b)
    WITH a, b, r, properties(r) AS props
    CREATE (a)-[r2:{new_type}]->(b)
    SET r2 = props
    DELETE r
    RETURN count(r2) as migrated
    """
    with driver.session(database=database) as session:
        result = session.run(migrate_query)
        migrated = result.single()["migrated"]

    print(f"  {old_type} -> {new_type}: {migrated} relationships migrated")
    return migrated


def run_migration(driver, database, dry_run=False):
    """Run all relationship renames."""
    total = 0
    for old_type, new_type in RELATIONSHIP_RENAMES.items():
        total += migrate_relationship(driver, database, old_type, new_type, dry_run)
    return total


def main():
    parser = argparse.ArgumentParser(
        description="Migrate Neo4j graph schema to new relationship names"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be migrated without making changes",
    )
    args = parser.parse_args()

    config = get_neo4j_config()
    driver = create_driver(config)

    mode = "DRY RUN" if args.dry_run else "LIVE"
    print(f"Schema migration ({mode})")
    print("=" * 50)

    total = run_migration(driver, config["database"], dry_run=args.dry_run)

    if args.dry_run:
        print(f"\nDry run complete: {total} relationships would be migrated")
    else:
        print(f"\nMigration complete: {total} relationships migrated")

    driver.close()


if __name__ == "__main__":
    main()
