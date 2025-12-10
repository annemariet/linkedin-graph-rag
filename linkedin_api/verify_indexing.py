#!/usr/bin/env python3
"""
Verify that LinkedIn content is properly indexed for GraphRAG.

This script checks:
1. Chunks exist in the database
2. Chunks have embeddings
3. Vector index is working
4. Sample content retrieval
"""

import os
import dotenv
from neo4j import GraphDatabase
from neo4j_graphrag.embeddings.vertexai import VertexAIEmbeddings

# Apply DNS fix before importing Google libraries
try:
    from linkedin_api.dns_utils import setup_gcp_dns_fix

    setup_gcp_dns_fix(use_custom_resolver=True)
except ImportError:
    pass

dotenv.load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "neoneoneo")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "textembedding-gecko@002")


def verify_chunks(driver):
    """Verify chunks exist and have properties."""
    print("\n" + "=" * 60)
    print("📦 CHUNK VERIFICATION")
    print("=" * 60)

    with driver.session(database=NEO4J_DATABASE) as session:
        # Count chunks
        total = session.run("MATCH (c:Chunk) RETURN count(c) as count").single()[
            "count"
        ]
        print(f"\n✅ Total Chunk nodes: {total}")

        if total == 0:
            print("   ❌ No chunks found! Run index_content.py first.")
            return False

        # Check chunks with embeddings
        with_embedding = session.run(
            "MATCH (c:Chunk) WHERE c.embedding IS NOT NULL RETURN count(c) as count"
        ).single()["count"]
        print(f"✅ Chunks with embeddings: {with_embedding}/{total}")

        if with_embedding == 0:
            print("   ❌ No chunks have embeddings!")
            return False

        # Check chunks with text
        with_text = session.run(
            "MATCH (c:Chunk) WHERE c.text IS NOT NULL RETURN count(c) as count"
        ).single()["count"]
        print(f"✅ Chunks with text: {with_text}/{total}")

        # Sample chunk properties
        print(f"\n📋 Sample chunk properties:")
        sample = session.run(
            """
            MATCH (c:Chunk) 
            WHERE c.embedding IS NOT NULL AND c.text IS NOT NULL
            RETURN c.id as id, 
                   size(c.text) as text_length,
                   size(c.embedding) as embedding_dim,
                   c.chunk_index as chunk_index,
                   c.source_urn as source_urn
            LIMIT 3
            """
        )
        for i, record in enumerate(sample, 1):
            print(f"\n   Chunk {i}:")
            print(f"     ID: {record['id']}")
            print(f"     Text length: {record['text_length']} chars")
            print(f"     Embedding dimensions: {record['embedding_dim']}")
            print(f"     Chunk index: {record['chunk_index']}")
            print(f"     Source URN: {record['source_urn']}")
            if record["text_length"]:
                text_preview = session.run(
                    "MATCH (c:Chunk {id: $id}) RETURN substring(c.text, 0, 100) as preview",
                    id=record["id"],
                ).single()["preview"]
                print(f"     Text preview: {text_preview}...")

        # Check relationships
        linked = session.run(
            "MATCH (c:Chunk)-[:FROM_CHUNK]->(s) RETURN count(DISTINCT c) as count"
        ).single()["count"]
        print(f"\n✅ Chunks linked to sources: {linked}/{total}")

        return True


def verify_vector_index(driver):
    """Verify vector index exists and is configured correctly."""
    print("\n" + "=" * 60)
    print("🔍 VECTOR INDEX VERIFICATION")
    print("=" * 60)

    with driver.session(database=NEO4J_DATABASE) as session:
        # List all vector indexes
        indexes = session.run("SHOW INDEXES WHERE type = 'VECTOR'")
        index_list = list(indexes)

        if not index_list:
            print("\n❌ No vector indexes found!")
            return None

        print(f"\n✅ Found {len(index_list)} vector index(es):")
        for idx in index_list:
            name = idx.get("name", "unknown")
            state = idx.get("state", "unknown")
            print(f"\n   Index: {name}")
            print(f"   State: {state}")

            # Get index details
            try:
                details = session.run("SHOW INDEX {name} YIELD *", name=name).single()
                if details:
                    print(f"   Type: {details.get('type', 'unknown')}")
                    print(f"   Entity type: {details.get('entityType', 'unknown')}")
                    print(f"   Properties: {details.get('properties', [])}")
            except Exception:
                pass

        return index_list[0].get("name") if index_list else None


def test_vector_search(driver, embedder, index_name: str):
    """Test vector search directly."""
    print("\n" + "=" * 60)
    print("🔍 VECTOR SEARCH TEST")
    print("=" * 60)

    if not index_name:
        print("\n❌ No vector index available for testing")
        return

    print(f"\n📝 Testing search with index: {index_name}")

    # Test queries
    test_queries = [
        "AI",
        "post",
        "machine learning",
    ]

    for query_text in test_queries:
        print(f"\n   Query: '{query_text}'")
        try:
            # Generate query embedding
            query_embedding = embedder.embed_query(query_text)
            print(
                f"   ✅ Generated query embedding ({len(query_embedding)} dimensions)"
            )

            # Search using Cypher - Neo4j 5.x vector index query syntax
            with driver.session(database=NEO4J_DATABASE) as session:
                # Try the standard vector index query
                try:
                    result = session.run(
                        f"""
                        CALL db.index.vector.queryNodes('{index_name}', $k, $queryVector)
                        YIELD node, score
                        RETURN node.id as id, 
                               node.text as text,
                               score,
                               node.source_urn as source_urn
                        LIMIT 3
                        """,
                        k=3,
                        queryVector=query_embedding,
                    )
                except Exception as query_error:
                    # Fallback for different Neo4j versions or index types
                    print(f"   ⚠️  Standard query failed: {str(query_error)}")
                    print(f"   Trying alternative query syntax...")
                    # Alternative: use index directly in MATCH
                    result = session.run(
                        f"""
                        MATCH (c:Chunk)
                        WHERE c.embedding IS NOT NULL
                        WITH c, vector.similarity.cosine(c.embedding, $queryVector) AS score
                        ORDER BY score DESC
                        LIMIT 3
                        RETURN c.id as id,
                               c.text as text,
                               score,
                               c.source_urn as source_urn
                        """,
                        queryVector=query_embedding,
                    )

                results = list(result)
                if results:
                    print(f"   ✅ Found {len(results)} results:")
                    for i, record in enumerate(results, 1):
                        score = record["score"]
                        text_preview = (record["text"] or "")[:80]
                        print(f"      {i}. Score: {score:.4f}")
                        print(f"         Text: {text_preview}...")
                        print(f"         Source: {record['source_urn']}")
                else:
                    print(f"   ⚠️  No results found")

        except Exception as e:
            print(f"   ❌ Error: {str(e)}")
            import traceback

            traceback.print_exc()


def check_source_nodes(driver):
    """Check if source Post/Comment nodes exist and are linked."""
    print("\n" + "=" * 60)
    print("🔗 SOURCE NODES VERIFICATION")
    print("=" * 60)

    with driver.session(database=NEO4J_DATABASE) as session:
        # Count source nodes
        posts = session.run("MATCH (p:Post) RETURN count(p) as count").single()["count"]
        comments = session.run("MATCH (c:Comment) RETURN count(c) as count").single()[
            "count"
        ]

        print(f"\n✅ Post nodes: {posts}")
        print(f"✅ Comment nodes: {comments}")

        # Check links
        linked_posts = session.run(
            "MATCH (c:Chunk)-[:FROM_CHUNK]->(p:Post) RETURN count(DISTINCT p) as count"
        ).single()["count"]
        linked_comments = session.run(
            "MATCH (c:Chunk)-[:FROM_CHUNK]->(c:Comment) RETURN count(DISTINCT c) as count"
        ).single()["count"]

        print(f"\n✅ Posts linked to chunks: {linked_posts}")
        print(f"✅ Comments linked to chunks: {linked_comments}")

        # Sample linked sources
        print(f"\n📋 Sample linked sources:")
        samples = session.run(
            """
            MATCH (c:Chunk)-[:FROM_CHUNK]->(s)
            WHERE c.embedding IS NOT NULL
            RETURN labels(s)[0] as label, 
                   s.urn as urn,
                   s.url as url,
                   count(c) as chunk_count
            LIMIT 5
            """
        )
        for i, record in enumerate(samples, 1):
            print(f"\n   {i}. {record['label']}:")
            print(f"      URN: {record['urn']}")
            print(f"      URL: {record.get('url', 'N/A')}")
            print(f"      Chunks: {record['chunk_count']}")


def main():
    """Main verification function."""
    print("🔍 LinkedIn Content Indexing Verification")
    print("=" * 60)

    # Connect to Neo4j
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))

    try:
        driver.verify_connectivity()
        print(f"\n✅ Connected to Neo4j")
        print(f"   Database: {NEO4J_DATABASE}")
    except Exception as e:
        print(f"\n❌ Connection failed: {str(e)}")
        return

    # Initialize embedder for testing
    try:
        print(f"\n🤖 Initializing embedder for testing...")
        embedder = VertexAIEmbeddings(model=EMBEDDING_MODEL)
        test_embedding = embedder.embed_query("test")
        print(f"   ✅ Embedder ready ({len(test_embedding)} dimensions)")
    except Exception as e:
        print(f"   ⚠️  Embedder initialization failed: {str(e)}")
        embedder = None

    # Run verifications
    chunks_ok = verify_chunks(driver)
    index_name = verify_vector_index(driver)
    check_source_nodes(driver)

    if chunks_ok and index_name and embedder:
        test_vector_search(driver, embedder, index_name)

    # Summary
    print("\n" + "=" * 60)
    print("📊 VERIFICATION SUMMARY")
    print("=" * 60)

    if not chunks_ok:
        print("\n❌ ISSUES FOUND:")
        print("   • Chunks are missing or don't have embeddings")
        print("   • Run index_content.py to create chunks")
    elif not index_name:
        print("\n❌ ISSUES FOUND:")
        print("   • Vector index is missing")
        print("   • Run index_content.py to create the index")
    else:
        print("\n✅ INDEXING APPEARS CORRECT")
        print("   • Chunks exist with embeddings")
        print("   • Vector index is configured")
        print("   • If queries still fail, check:")
        print("     - Query embeddings match chunk embeddings")
        print("     - Index name matches in query script")
        print("     - Database name is consistent")

    driver.close()


if __name__ == "__main__":
    main()
