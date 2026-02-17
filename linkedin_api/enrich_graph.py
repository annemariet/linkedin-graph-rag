#!/usr/bin/env python3
"""
Phase B: LLM-powered graph enrichment using SimpleKGPipeline.

Fetches posts/comments that have content but haven't been enriched yet,
runs them through the SimpleKGPipeline to extract entities (Technology,
Concept, Resource, etc.) and relationships.

Usage:
  uv run python -m linkedin_api.enrich_graph [--limit N]
"""

import argparse
import asyncio
import logging

import dotenv

from linkedin_api.build_graph import create_driver, get_neo4j_config
from linkedin_api.graph_schema import get_pipeline_schema
from linkedin_api.llm_config import create_llm

dotenv.load_dotenv()

logger = logging.getLogger(__name__)


class _NoOpEmbedder:
    """Placeholder embedder for enrichment pipeline.

    The enrichment pipeline only needs the LLM for entity extraction.
    Real embeddings are handled separately by index_content.py.
    Inherits from neo4j_graphrag's Embedder ABC to satisfy pydantic validation.
    """

    def __init__(self):
        from neo4j_graphrag.embeddings.base import Embedder

        # Register as virtual subclass so isinstance() checks pass
        Embedder.register(type(self))

    def embed_query(self, text: str) -> list[float]:
        return [0.0]


def create_kg_pipeline(driver, database):
    """Create a SimpleKGPipeline configured with the graph schema."""
    from neo4j_graphrag.experimental.components.text_splitters.fixed_size_splitter import (
        FixedSizeSplitter,
    )
    from neo4j_graphrag.experimental.pipeline.kg_builder import SimpleKGPipeline

    schema = get_pipeline_schema()

    return SimpleKGPipeline(
        llm=create_llm(),
        driver=driver,
        neo4j_database=database,
        embedder=_NoOpEmbedder(),
        from_pdf=False,
        text_splitter=FixedSizeSplitter(chunk_size=500, chunk_overlap=100),
        entities=schema["entities"],
        relations=schema["relations"],
        potential_schema=schema["potential_schema"],
    )


def get_posts_needing_enrichment(driver, database, limit=None):
    """Fetch posts with content that haven't been enriched yet."""
    query = """
    MATCH (p:Post)
    WHERE p.content IS NOT NULL AND p.content <> ''
      AND p.enriched IS NULL
    RETURN p.urn AS urn, p.content AS content, p.url AS url
    """
    if limit:
        query += f" LIMIT {limit}"

    with driver.session(database=database) as session:
        result = session.run(query)
        return [dict(record) for record in result]


def get_comments_needing_enrichment(driver, database, limit=None):
    """Fetch comments with text that haven't been enriched yet."""
    query = """
    MATCH (c:Comment)
    WHERE c.text IS NOT NULL AND c.text <> ''
      AND c.enriched IS NULL
    RETURN c.urn AS urn, c.text AS content
    """
    if limit:
        query += f" LIMIT {limit}"

    with driver.session(database=database) as session:
        result = session.run(query)
        return [dict(record) for record in result]


def mark_as_enriched(driver, urn, database):
    """Mark a node as enriched so it's not processed again."""
    query = """
    MATCH (n {urn: $urn})
    SET n.enriched = true
    """
    with driver.session(database=database) as session:
        session.run(query, urn=urn)


async def enrich_graph(driver, database, limit=None):
    """Fetch posts/comments needing enrichment, run SimpleKGPipeline."""
    pipeline = create_kg_pipeline(driver, database)

    posts = get_posts_needing_enrichment(driver, database, limit=limit)
    comments = get_comments_needing_enrichment(driver, database, limit=limit)
    nodes = posts + comments

    if not nodes:
        print("No posts or comments need enrichment.")
        return

    print(
        f"Enriching {len(nodes)} nodes ({len(posts)} posts, {len(comments)} comments)"
    )

    success = 0
    failed = 0

    for i, node in enumerate(nodes, 1):
        urn = node["urn"]
        content = node["content"]
        if not content or len(content.strip()) < 20:
            continue

        print(f"  [{i}/{len(nodes)}] {urn[:60]}...")

        try:
            await pipeline.run_async(text=content)
            mark_as_enriched(driver, urn, database)
            success += 1
        except Exception as e:
            print(f"Failed to enrich {urn}: {e}")
            logger.warning(f"Failed to enrich {urn}: {e}")
            failed += 1

    print(f"Enrichment complete: {success} succeeded, {failed} failed")


def main():
    parser = argparse.ArgumentParser(description="Enrich graph with LLM extraction")
    parser.add_argument("--limit", type=int, default=None, help="Max nodes to enrich")
    args = parser.parse_args()

    config = get_neo4j_config()
    driver = create_driver(config)

    try:
        asyncio.run(enrich_graph(driver, config["database"], limit=args.limit))
    finally:
        driver.close()


if __name__ == "__main__":
    main()
