import dotenv
from os import getenv
from neo4j import GraphDatabase
import json


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


def create_nodes_batch(tx, nodes_batch):
    """Create nodes with dynamic labels and properties using standard Cypher."""
    created = 0
    for node in nodes_batch:
        labels_str = ":".join(node["labels"])
        query = f"CREATE (n:{labels_str}) SET n = $props RETURN n"
        tx.run(query, props=node["properties"])
        created += 1
    return created


def create_relationships_batch(tx, rels_batch):
    """Create relationships with dynamic type and properties using standard Cypher."""
    created = 0
    for rel in rels_batch:
        rel_type = rel["type"]
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


def load_graph_data(driver, json_file):
    """Load nodes and relationships from JSON into Neo4j."""
    with open(json_file, "r") as f:
        data = json.load(f)

    nodes = data.get("nodes", [])
    relationships = data.get("relationships", [])

    print(f"Loading {len(nodes)} nodes and {len(relationships)} relationships...")

    # Create nodes in batches
    with driver.session() as session:
        for i in range(0, len(nodes), BATCH_SIZE):
            batch = nodes[i : i + BATCH_SIZE]
            count = session.execute_write(create_nodes_batch, batch)
            print(f"Created {count} nodes (batch {i // BATCH_SIZE + 1})")

    # Create relationships in batches
    with driver.session() as session:
        for i in range(0, len(relationships), BATCH_SIZE):
            batch = relationships[i : i + BATCH_SIZE]
            count = session.execute_write(create_relationships_batch, batch)
            print(f"Created {count} relationships (batch {i // BATCH_SIZE + 1})")

    print("Graph built successfully!")


if __name__ == "__main__":
    import sys
    import glob

    # Get JSON filename from command line or find most recent neo4j_data file
    if len(sys.argv) > 1:
        json_file = sys.argv[1]
    else:
        # Find most recent neo4j_data_*.json file
        files = glob.glob("neo4j_data_*.json")
        if files:
            json_file = max(files)  # Most recent by filename (timestamp in name)
            print(f"📂 Using most recent file: {json_file}")
        else:
            # Fallback to old filename
            json_file = "neo4j_data.json"
            print(f"📂 Using default file: {json_file}")

    db_cleanup(driver)
    load_graph_data(driver, json_file)
    driver.close()
