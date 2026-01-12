#!/usr/bin/env python3
"""
Index LinkedIn post and comment content for GraphRAG.

This script:
1. Fetches Post and Comment nodes from Neo4j
2. Extracts content from their URLs
3. Creates Chunk nodes with embeddings
4. Links chunks to posts/comments
5. Creates vector index for GraphRAG retrieval
"""

import os
import dotenv
from typing import Optional, List, Dict
from bs4 import BeautifulSoup
import requests
from neo4j import GraphDatabase

# Apply DNS fix before importing Google libraries
try:
    from linkedin_api.dns_utils import setup_gcp_dns_fix

    setup_gcp_dns_fix(use_custom_resolver=True)
except ImportError:
    pass

from neo4j_graphrag.embeddings.vertexai import VertexAIEmbeddings
from neo4j_graphrag.indexes import create_vector_index

dotenv.load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "neoneoneo")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

# Embedding configuration
# Using textembedding-gecko@002 (lightweight, stable) or textembedding-gecko (latest)
# Note: @003 is deprecated, @002 is more widely available
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "textembedding-gecko@002")
VECTOR_INDEX_NAME = "linkedin_content_index"
CHUNK_SIZE = 500  # Characters per chunk
CHUNK_OVERLAP = 100  # Overlap between chunks
EMBEDDING_DIMENSIONS = 768  # Standard for gecko models


def extract_post_content(url: str) -> Optional[str]:
    """
    Extract text content from a LinkedIn post URL.

    Args:
        url: LinkedIn post URL

    Returns:
        Extracted text content or None if extraction fails
    """
    try:
        response = requests.get(url, timeout=10, allow_redirects=True)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # Try to find post content - LinkedIn uses various selectors
        # Common patterns for LinkedIn post content
        content_selectors = [
            "article[data-id]",
            ".feed-shared-update-v2__description",
            ".feed-shared-text",
            '[data-test-id="main-feed-activity-card"]',
        ]

        content_text = []

        # Try each selector
        for selector in content_selectors:
            elements = soup.select(selector)
            if elements:
                for elem in elements:
                    text = elem.get_text(strip=True)
                    if text and len(text) > 20:  # Filter out very short text
                        content_text.append(text)

        # Fallback: extract from meta tags
        if not content_text:
            og_description = soup.find("meta", property="og:description")
            if og_description:
                content_text.append(og_description.get("content", ""))

            # Try title as fallback
            title = soup.find("title")
            if title:
                title_text = title.get_text(strip=True)
                # LinkedIn titles often contain post content before " | "
                if " | " in title_text:
                    content_text.append(title_text.split(" | ")[0])

        if content_text:
            return "\n".join(content_text)

        return None

    except Exception as e:
        print(f"   ⚠️  Error extracting content from {url}: {str(e)}")
        return None


def split_text_into_chunks(
    text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP
) -> List[str]:
    """
    Split text into overlapping chunks.

    Args:
        text: Text to split
        chunk_size: Size of each chunk
        overlap: Overlap between chunks

    Returns:
        List of text chunks
    """
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]

        # Try to break at sentence boundary if possible
        if end < len(text):
            # Look for sentence endings
            for punct in [". ", ".\n", "! ", "!\n", "? ", "?\n"]:
                last_punct = chunk.rfind(punct)
                if (
                    last_punct > chunk_size * 0.7
                ):  # Only break if we're past 70% of chunk
                    chunk = chunk[: last_punct + 1]
                    end = start + last_punct + 1
                    break

        chunks.append(chunk.strip())
        start = end - overlap

    return chunks


def get_posts_and_comments(driver) -> List[Dict]:
    """
    Fetch Post and Comment nodes with URLs from Neo4j that haven't been indexed yet.

    Filters out posts/comments that already have Chunk nodes linked via FROM_CHUNK
    to enable incremental loading without duplicates.

    Returns:
        List of nodes with their URLs that need indexing
    """
    query = """
    MATCH (n)
    WHERE (n:Post OR n:Comment)
      AND n.url IS NOT NULL
      AND n.url <> ''
      AND NOT EXISTS {
        MATCH (n)<-[:FROM_CHUNK]-(:Chunk)
      }
    RETURN n.urn as urn, n.url as url, labels(n) as labels, n.post_id as post_id, n.comment_id as comment_id
    """

    with driver.session(database=NEO4J_DATABASE) as session:
        result = session.run(query)
        nodes = []
        for record in result:
            nodes.append(
                {
                    "urn": record["urn"],
                    "url": record["url"],
                    "labels": record["labels"],
                    "post_id": record.get("post_id"),
                    "comment_id": record.get("comment_id"),
                }
            )
        return nodes


def create_chunk_node(
    tx, chunk_id: str, text: str, source_urn: str, chunk_index: int, total_chunks: int
):
    """
    Create or update a Chunk node and link it to the source Post/Comment.

    Uses MERGE to avoid duplicates if the chunk already exists, updating
    its properties if needed. Returns the internal Neo4j node ID for use with upsert_vectors.
    """
    query = """
    MATCH (source {urn: $source_urn})
    MERGE (chunk:Chunk {id: $chunk_id})
    SET chunk.text = $text,
        chunk.chunk_index = $chunk_index,
        chunk.total_chunks = $total_chunks,
        chunk.source_urn = $source_urn
    MERGE (chunk)-[:FROM_CHUNK]->(source)
    RETURN id(chunk) as node_id, chunk.id as chunk_id
    """
    result = tx.run(
        query,
        chunk_id=chunk_id,
        text=text,
        source_urn=source_urn,
        chunk_index=chunk_index,
        total_chunks=total_chunks,
    )
    record = result.single()
    if record:
        return record["node_id"]  # Return internal Neo4j node ID
    raise RuntimeError(f"Failed to create chunk node {chunk_id}")


def index_content_for_graphrag(
    driver, embedder, embedding_dimensions: int, limit: Optional[int] = None
):
    """
    Main function to index post and comment content for GraphRAG.

    Supports incremental loading: only processes posts/comments that don't already
    have Chunk nodes linked via FROM_CHUNK relationships, preventing duplicates.

    Args:
        driver: Neo4j driver
        embedder: Embedding model
        embedding_dimensions: Number of dimensions for embeddings
        limit: Optional limit on number of posts/comments to process
    """
    print("🔍 Fetching unindexed posts and comments from Neo4j...")
    nodes = get_posts_and_comments(driver)

    if limit:
        nodes = nodes[:limit]

    if len(nodes) == 0:
        print("✅ No new posts/comments to index (all already indexed)")
        return

    print(f"✅ Found {len(nodes)} unindexed posts/comments to index")

    # Create vector index per Neo4j GraphRAG docs
    # Reference: https://neo4j.com/docs/neo4j-graphrag-python/current/user_guide_rag.html#create-a-vector-index
    print(f"\n📊 Creating vector index '{VECTOR_INDEX_NAME}'...")
    create_vector_index(
        driver,
        VECTOR_INDEX_NAME,
        label="Chunk",
        embedding_property="embedding",
        dimensions=embedding_dimensions,
        similarity_fn="cosine",
    )
    print(f"   ✅ Vector index created")

    # Process each node
    processed = 0
    failed = 0
    total_chunks_created = 0

    for i, node in enumerate(nodes, 1):
        urn = node["urn"]
        url = node["url"]
        labels = node["labels"]

        print(f"\n[{i}/{len(nodes)}] Processing {labels[0]}: {urn[:50]}...")
        print(f"   URL: {url}")

        # Extract content
        content = extract_post_content(url)

        if not content:
            print(f"   ⚠️  No content extracted")
            failed += 1
            continue

        print(f"   ✅ Extracted {len(content)} characters")

        # Split into chunks
        chunks = split_text_into_chunks(content, CHUNK_SIZE, CHUNK_OVERLAP)
        print(f"   📝 Split into {len(chunks)} chunks")

        # Create chunk nodes and embeddings
        chunk_embeddings = []
        chunk_ids = []  # Custom id property for reference
        node_ids = []  # Internal Neo4j node IDs for upsert_vectors

        for chunk_idx, chunk_text in enumerate(chunks):
            chunk_id = f"{urn}_chunk_{chunk_idx}"
            chunk_ids.append(chunk_id)

            # Create chunk node and get internal Neo4j node ID
            with driver.session(database=NEO4J_DATABASE) as session:
                node_id = session.execute_write(
                    create_chunk_node, chunk_id, chunk_text, urn, chunk_idx, len(chunks)
                )
                node_ids.append(node_id)

            # Generate embedding - fail immediately on error
            try:
                embedding = embedder.embed_query(chunk_text)
                if not embedding or len(embedding) == 0:
                    raise ValueError("Empty embedding returned")
                chunk_embeddings.append(embedding)
            except Exception as e:
                print(
                    f"\n❌ FATAL ERROR: Failed to generate embedding for chunk {chunk_idx}"
                )
                print(f"   Error: {str(e)}")
                print(f"   Model: {EMBEDDING_MODEL}")
                print(f"   Chunk text (first 100 chars): {chunk_text[:100]}...")
                print(f"\n💡 Troubleshooting:")
                print(
                    f"   1. Verify the model '{EMBEDDING_MODEL}' is available in your project"
                )
                print(f"   2. Check Google Cloud credentials are properly configured")
                print(
                    f"   3. Try a different model: textembedding-gecko@002 or textembedding-gecko"
                )
                raise RuntimeError(f"Embedding generation failed: {str(e)}") from e

        # Store embeddings using direct Cypher SET
        # Note: upsert_vectors may not support database parameter, so we use Cypher directly
        # Neo4j automatically updates vector indexes when indexed properties are SET
        if chunk_embeddings:
            print(f"   💾 Storing {len(chunk_embeddings)} embeddings...")
            with driver.session(database=NEO4J_DATABASE) as session:
                # Verify nodes exist before updating
                verify_result = session.run(
                    "MATCH (c:Chunk) WHERE id(c) IN $node_ids RETURN count(c) as count",
                    node_ids=node_ids,
                ).single()
                if verify_result["count"] != len(node_ids):
                    print(
                        f"   ⚠️  Warning: Only {verify_result['count']}/{len(node_ids)} nodes found"
                    )

                # Update embeddings using internal node IDs
                result = session.run(
                    """
                    UNWIND $data AS item
                    MATCH (c:Chunk)
                    WHERE id(c) = item.node_id
                    SET c.embedding = item.embedding
                    RETURN count(c) as updated
                    """,
                    data=[
                        {"node_id": node_id, "embedding": embedding}
                        for node_id, embedding in zip(node_ids, chunk_embeddings)
                    ],
                )
                updated_count = result.single()["updated"]
                if updated_count != len(chunk_ids):
                    raise RuntimeError(
                        f"Only {updated_count}/{len(chunk_ids)} chunks updated"
                    )

                # Verify embeddings were stored
                verify_embeddings = session.run(
                    "MATCH (c:Chunk) WHERE id(c) IN $node_ids AND c.embedding IS NOT NULL RETURN count(c) as count",
                    node_ids=node_ids,
                ).single()["count"]
                if verify_embeddings != len(node_ids):
                    raise RuntimeError(
                        f"Verification failed: Only {verify_embeddings}/{len(node_ids)} embeddings stored"
                    )

            print(f"   ✅ Stored and verified {len(chunk_embeddings)} embeddings")
            total_chunks_created += len(chunk_ids)

        processed += 1

    # Verify embeddings were stored
    print(f"\n🔍 Verifying embeddings were stored...")
    with driver.session(database=NEO4J_DATABASE) as session:
        total_chunks = session.run("MATCH (c:Chunk) RETURN count(c) as count").single()[
            "count"
        ]
        chunks_with_embedding = session.run(
            "MATCH (c:Chunk) WHERE c.embedding IS NOT NULL RETURN count(c) as count"
        ).single()["count"]
        sample_chunk = session.run(
            "MATCH (c:Chunk) WHERE c.embedding IS NOT NULL RETURN c.id as id, size(c.embedding) as dims LIMIT 1"
        ).single()

        print(f"   Total Chunk nodes: {total_chunks}")
        print(f"   Chunks with embeddings: {chunks_with_embedding}")
        if sample_chunk:
            print(f"   Sample chunk embedding dimensions: {sample_chunk['dims']}")

        if chunks_with_embedding == 0:
            print(f"\n   ⚠️  WARNING: No embeddings found in chunks!")
            print(f"   This means vector search won't work.")
        elif chunks_with_embedding < total_chunks:
            print(
                f"\n   ⚠️  WARNING: {total_chunks - chunks_with_embedding} chunks are missing embeddings"
            )

    print(f"\n{'='*60}")
    print(f"📊 INDEXING SUMMARY")
    print(f"{'='*60}")
    print(f"   Processed: {processed}/{len(nodes)}")
    print(f"   Failed: {failed}/{len(nodes)}")
    print(f"   Total chunks created: {total_chunks_created}")
    print(f"   Chunks with embeddings: {chunks_with_embedding}")
    print(f"\n✅ Content indexing complete!")
    print(f"💡 You can now use GraphRAG to query this content")


def main():
    """Main entry point."""
    import sys

    # Parse command line arguments
    limit = None
    if len(sys.argv) > 1:
        if sys.argv[1] in ["-h", "--help"]:
            print("Usage: index_content.py [--limit N]")
            print("\nOptions:")
            print(
                "  --limit N    Process only the first N posts/comments (for testing)"
            )
            print("  -h, --help  Show this help message")
            print("\nExamples:")
            print("  uv run linkedin_api/index_content.py           # Process all")
            print("  uv run linkedin_api/index_content.py --limit 5  # Process first 5")
            return
        elif sys.argv[1] == "--limit" and len(sys.argv) > 2:
            try:
                limit = int(sys.argv[2])
                print(f"⚠️  LIMIT MODE: Processing only first {limit} items")
            except ValueError:
                print(f"❌ Invalid limit value: {sys.argv[2]}")
                print("Usage: index_content.py [--limit N]")
                return

    print("🚀 LinkedIn Content Indexing for GraphRAG")
    print("=" * 60)
    if limit:
        print(f"🧪 TEST MODE: Limited to {limit} items")

    # Connect to Neo4j
    print(f"\n🔌 Connecting to Neo4j...")
    print(f"   URI: {NEO4J_URI}")
    print(f"   Database: {NEO4J_DATABASE}")

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))

    try:
        driver.verify_connectivity()
        print("   ✅ Connected successfully")
    except Exception as e:
        print(f"   ❌ Connection failed: {str(e)}")
        return

    # Initialize embedder - fail immediately on error
    print(f"\n🤖 Initializing embedding model...")
    print(f"   Model: {EMBEDDING_MODEL}")
    try:
        embedder = VertexAIEmbeddings(model=EMBEDDING_MODEL)
        # Test the embedder with a simple query to verify it works and get actual dimensions
        test_embedding = embedder.embed_query("test")
        if not test_embedding or len(test_embedding) == 0:
            raise ValueError("Embedder returned empty test embedding")

        # Get actual dimensions from the embedder
        actual_dimensions = len(test_embedding)
        print(f"   ✅ Embedder initialized and tested successfully")
        print(f"   Actual dimensions: {actual_dimensions}")

        # Warn if different from expected, but use actual dimensions
        if actual_dimensions != EMBEDDING_DIMENSIONS:
            msg = (
                f"   ⚠️  Note: Using actual dimensions ({actual_dimensions}) "
                f"instead of default ({EMBEDDING_DIMENSIONS})"
            )
            print(msg)
    except Exception as e:
        print(f"\n❌ FATAL ERROR: Failed to initialize embedder")
        print(f"   Error: {str(e)}")
        print(f"   Model: {EMBEDDING_MODEL}")
        print(f"\n💡 Troubleshooting:")
        print(
            f"   1. Verify the model '{EMBEDDING_MODEL}' is available in your Vertex AI project"
        )
        print(
            f"   2. Check GOOGLE_APPLICATION_CREDENTIALS is set or authentication is configured"
        )
        print(
            f"   3. Try a different model: textembedding-gecko@002 or textembedding-gecko"
        )
        print(f"   4. Ensure Vertex AI API is enabled in your Google Cloud project")
        driver.close()
        raise RuntimeError(f"Embedder initialization failed: {str(e)}") from e

    # Index content
    try:
        index_content_for_graphrag(driver, embedder, actual_dimensions, limit=limit)
    finally:
        driver.close()
        print("\n🔌 Connection closed")


if __name__ == "__main__":
    main()
