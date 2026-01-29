#!/usr/bin/env python3
"""
Index LinkedIn post and comment content for GraphRAG.

This script:
1. Fetches Post and Comment nodes from Neo4j
2. Extracts content from their URLs
3. Creates Chunk nodes with embeddings
4. Links chunks to posts/comments
5. Creates vector index for GraphRAG retrieval

Supports incremental indexing: only processes posts/comments without existing Chunk nodes.
"""

import os
import sys
import logging
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

# Module-level logger (configured in main() when run as script)
logger = logging.getLogger(__name__)

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
BATCH_SIZE = 50  # Number of chunks to process per batch


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


def create_chunks_batch(tx, chunks_data: List[Dict]) -> List[str]:
    """
    Create or update multiple Chunk nodes in a single transaction.

    Uses MERGE to avoid duplicates if chunks already exist.
    Returns the chunk IDs for reference.

    Args:
        tx: Neo4j transaction
        chunks_data: List of dicts with chunk_id, text, source_urn, chunk_index, total_chunks
    """
    query = """
    UNWIND $chunks AS chunk_data
    MATCH (source {urn: chunk_data.source_urn})
    MERGE (chunk:Chunk {id: chunk_data.chunk_id})
    SET chunk.text = chunk_data.text,
        chunk.chunk_index = chunk_data.chunk_index,
        chunk.total_chunks = chunk_data.total_chunks,
        chunk.source_urn = chunk_data.source_urn
    MERGE (chunk)-[:FROM_CHUNK]->(source)
    RETURN chunk.id as chunk_id
    """
    result = tx.run(query, chunks=chunks_data)
    return [record["chunk_id"] for record in result]


def store_embeddings_batch(tx, embeddings_data: List[Dict]) -> int:
    """
    Store embeddings for multiple chunks in a single transaction.

    Args:
        tx: Neo4j transaction
        embeddings_data: List of dicts with chunk_id and embedding

    Returns:
        Number of chunks updated
    """
    query = """
    UNWIND $data AS item
    MATCH (c:Chunk {id: item.chunk_id})
    SET c.embedding = item.embedding
    RETURN count(c) as updated
    """
    result = tx.run(query, data=embeddings_data)
    return result.single()["updated"]


def index_content_for_graphrag(
    driver,
    embedder,
    embedding_dimensions: int,
    limit: Optional[int] = None,
    verbose: bool = False,
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
        verbose: If True, print detailed progress for each item
    """
    logger.info("🔍 Fetching unindexed posts and comments from Neo4j...")
    nodes = get_posts_and_comments(driver)

    if limit:
        nodes = nodes[:limit]

    if len(nodes) == 0:
        logger.info("✅ No new posts/comments to index (all already indexed)")
        return

    logger.info(f"✅ Found {len(nodes)} unindexed posts/comments to index")

    # Create vector index per Neo4j GraphRAG docs
    logger.info(f"\n📊 Creating vector index '{VECTOR_INDEX_NAME}'...")
    create_vector_index(
        driver,
        VECTOR_INDEX_NAME,
        label="Chunk",
        embedding_property="embedding",
        dimensions=embedding_dimensions,
        similarity_fn="cosine",
    )
    logger.info("   ✅ Vector index created/verified")

    # Process nodes and collect all chunks
    processed = 0
    failed = 0
    pending_chunks: List[Dict] = []  # Chunks waiting to be written
    pending_embeddings: List[Dict] = []  # Embeddings waiting to be stored

    for i, node in enumerate(nodes, 1):
        urn = node["urn"]
        url = node["url"]
        labels = node["labels"]

        # Progress indicator (compact)
        if verbose:
            logger.info(f"\n[{i}/{len(nodes)}] {labels[0]}: {urn[:50]}...")
        elif i == 1 or i % 10 == 0 or i == len(nodes):
            logger.info(f"   Processing {i}/{len(nodes)}...")

        # Extract content
        content = extract_post_content(url)

        if not content:
            if verbose:
                logger.warning(f"   ⚠️  No content extracted from {url}")
            failed += 1
            continue

        # Split into chunks
        chunks = split_text_into_chunks(content, CHUNK_SIZE, CHUNK_OVERLAP)

        if verbose:
            logger.info(f"   ✅ {len(content)} chars → {len(chunks)} chunks")

        # Prepare chunk data and generate embeddings
        for chunk_idx, chunk_text in enumerate(chunks):
            chunk_id = f"{urn}_chunk_{chunk_idx}"

            # Add to pending chunks
            pending_chunks.append(
                {
                    "chunk_id": chunk_id,
                    "text": chunk_text,
                    "source_urn": urn,
                    "chunk_index": chunk_idx,
                    "total_chunks": len(chunks),
                }
            )

            # Generate embedding
            try:
                embedding = embedder.embed_query(chunk_text)
                if not embedding or len(embedding) == 0:
                    raise ValueError("Empty embedding returned")
                pending_embeddings.append(
                    {
                        "chunk_id": chunk_id,
                        "embedding": embedding,
                    }
                )
            except Exception as e:
                logger.error(f"\n❌ FATAL: Embedding failed for {chunk_id}")
                logger.error(f"   Error: {str(e)}")
                logger.error(f"   Model: {EMBEDDING_MODEL}")
                raise RuntimeError(f"Embedding generation failed: {str(e)}") from e

        # Flush batch if it's large enough
        if len(pending_chunks) >= BATCH_SIZE:
            _flush_batch(driver, pending_chunks, pending_embeddings, verbose)
            pending_chunks.clear()
            pending_embeddings.clear()

        processed += 1

    # Flush remaining chunks
    if pending_chunks:
        _flush_batch(driver, pending_chunks, pending_embeddings, verbose)

    # Final verification
    _print_summary(driver, processed, failed, len(nodes))


def _flush_batch(
    driver, chunks_data: List[Dict], embeddings_data: List[Dict], verbose: bool
):
    """Write a batch of chunks and their embeddings to Neo4j."""
    if not chunks_data:
        return

    with driver.session(database=NEO4J_DATABASE) as session:
        # Create chunk nodes
        created_ids = session.execute_write(create_chunks_batch, chunks_data)

        if len(created_ids) != len(chunks_data):
            logger.warning(
                f"   ⚠️  Created {len(created_ids)}/{len(chunks_data)} chunks"
            )

        # Store embeddings
        updated = session.execute_write(store_embeddings_batch, embeddings_data)

        if updated != len(embeddings_data):
            raise RuntimeError(
                f"Only {updated}/{len(embeddings_data)} embeddings stored"
            )

    if verbose:
        logger.info(f"   💾 Batch: {len(chunks_data)} chunks written")


def _print_summary(driver, processed: int, failed: int, total: int):
    """Print final indexing summary with verification."""
    with driver.session(database=NEO4J_DATABASE) as session:
        total_chunks = session.run("MATCH (c:Chunk) RETURN count(c) as count").single()[
            "count"
        ]
        chunks_with_embedding = session.run(
            "MATCH (c:Chunk) WHERE c.embedding IS NOT NULL RETURN count(c) as count"
        ).single()["count"]
        sample = session.run(
            "MATCH (c:Chunk) WHERE c.embedding IS NOT NULL "
            "RETURN c.id as id, size(c.embedding) as dims LIMIT 1"
        ).single()

    logger.info(f"\n{'='*60}")
    logger.info("📊 INDEXING SUMMARY")
    logger.info(f"{'='*60}")
    logger.info(f"   Processed: {processed}/{total}")
    logger.info(f"   Failed (no content): {failed}/{total}")
    logger.info(f"   Total chunks in DB: {total_chunks}")
    logger.info(f"   Chunks with embeddings: {chunks_with_embedding}")
    if sample:
        logger.info(f"   Embedding dimensions: {sample['dims']}")

    if chunks_with_embedding == 0:
        logger.warning(
            "\n   ⚠️  WARNING: No embeddings found! Vector search won't work."
        )
    elif chunks_with_embedding < total_chunks:
        logger.warning(
            f"\n   ⚠️  WARNING: {total_chunks - chunks_with_embedding} chunks missing embeddings"
        )

    logger.info("\n✅ Content indexing complete!")
    logger.info("💡 Run query_graphrag to search this content")


def _configure_logging():
    """Configure logging for CLI usage (only if not already configured)."""
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)


def main():
    """Main entry point."""
    import argparse

    _configure_logging()

    parser = argparse.ArgumentParser(
        description="Index LinkedIn content for GraphRAG",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  uv run python -m linkedin_api.index_content           # Process all unindexed
  uv run python -m linkedin_api.index_content --limit 5 # Process first 5
  uv run python -m linkedin_api.index_content -v        # Verbose output
        """,
    )
    parser.add_argument(
        "--limit", "-l", type=int, help="Process only first N items (for testing)"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show detailed progress per item"
    )
    args = parser.parse_args()

    logger.info("🚀 LinkedIn Content Indexing for GraphRAG")
    logger.info("=" * 60)
    if args.limit:
        logger.info(f"🧪 TEST MODE: Limited to {args.limit} items")
    if args.verbose:
        logger.info("📢 Verbose mode enabled")

    # Connect to Neo4j
    logger.info(f"\n🔌 Connecting to Neo4j at {NEO4J_URI}...")

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))

    try:
        driver.verify_connectivity()
        logger.info("   ✅ Connected")
    except Exception as e:
        logger.error(f"   ❌ Connection failed: {str(e)}")
        return

    # Initialize embedder
    logger.info(f"\n🤖 Initializing embedder ({EMBEDDING_MODEL})...")
    try:
        embedder = VertexAIEmbeddings(model=EMBEDDING_MODEL)
        test_embedding = embedder.embed_query("test")
        if not test_embedding or len(test_embedding) == 0:
            raise ValueError("Embedder returned empty test embedding")

        actual_dimensions = len(test_embedding)
        logger.info(f"   ✅ Ready (dimensions: {actual_dimensions})")

        if actual_dimensions != EMBEDDING_DIMENSIONS:
            logger.info(
                f"   Note: Using {actual_dimensions} dims (default: {EMBEDDING_DIMENSIONS})"
            )
    except Exception as e:
        logger.error(f"\n❌ FATAL: Embedder initialization failed")
        logger.error(f"   Error: {str(e)}")
        logger.error(f"\n💡 Check: model availability, GCP credentials, Vertex AI API")
        driver.close()
        raise RuntimeError(f"Embedder initialization failed: {str(e)}") from e

    # Index content
    try:
        index_content_for_graphrag(
            driver, embedder, actual_dimensions, limit=args.limit, verbose=args.verbose
        )
    finally:
        driver.close()
        logger.info("\n🔌 Connection closed")


if __name__ == "__main__":
    main()
