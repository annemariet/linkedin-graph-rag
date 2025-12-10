# LinkedIn GraphRAG Setup

This guide explains how to index LinkedIn post and comment content for GraphRAG queries.

## Overview

The GraphRAG system indexes the text content of LinkedIn posts and comments, creates embeddings, and enables semantic search over your LinkedIn activity.

## Prerequisites

1. **Neo4j Database**: Your LinkedIn graph must already be loaded into Neo4j (use `build_graph.py`)
2. **Google Cloud Credentials**: For embeddings and LLM (Vertex AI)
   - Set `GOOGLE_APPLICATION_CREDENTIALS` environment variable, or
   - Configure application default credentials
   - Ensure `neo4j-graphrag[google]` is installed: `pip install "neo4j-graphrag[google]"`
3. **Environment Variables**:
   ```bash
   NEO4J_URI=neo4j://localhost:7687
   NEO4J_USERNAME=neo4j
   NEO4J_PASSWORD=your_password
   NEO4J_DATABASE=neo4j
   EMBEDDING_MODEL=textembedding-gecko@002  # Optional, default (lightweight, stable)
   LLM_MODEL=gemini-1.5-pro  # Optional, default
   ```

## Step 1: Index Content

Run the indexing script to extract content from LinkedIn URLs and create embeddings:

```bash
# Process all posts/comments
uv run linkedin_api/index_content.py

# Quick test: process only first 5 items
uv run linkedin_api/index_content.py --limit 5
```

This script will:
- Fetch all Post and Comment nodes with URLs from Neo4j
- Extract text content from each URL
- Split content into chunks (500 chars with 100 char overlap)
- Create Chunk nodes linked to posts/comments
- Generate embeddings using Google Vertex AI
- Create/update vector index for fast retrieval

**Quick Testing**: Use `--limit N` to process only the first N items for faster testing. This is useful for:
- Verifying the indexing process works
- Testing embedding generation
- Checking index creation
- Debugging issues

**Note**: The script processes all posts/comments by default. Use `--limit` for quick testing.

## Step 1.5: Verify Indexing (Optional but Recommended)

Before querying, verify that content was indexed correctly:

```bash
uv run linkedin_api/verify_indexing.py
```

This will check:
- Chunks exist and have embeddings
- Vector index is configured correctly
- Source nodes are linked properly
- Vector search works directly

## Step 2: Query with GraphRAG

### Interactive Mode

Run the query script without arguments for interactive mode:

```bash
uv run linkedin_api/query_graphrag.py
```

Commands:
- Type your question and press Enter
- `cypher` - Toggle between Vector and Vector+Cypher retrievers
- `topk <number>` - Set number of results to retrieve
- `quit` or `exit` - Exit

### Command Line Mode

Query directly from command line:

```bash
uv run linkedin_api/query_graphrag.py "What posts did I react to about AI?"
```

Add `--cypher` flag to use graph traversal:

```bash
uv run linkedin_api/query_graphrag.py --cypher "What are the main topics in posts I commented on?"
```

## Retrievers

### Vector Retriever

Simple semantic search over chunk embeddings. Fast and good for direct content queries.

### Vector + Cypher Retriever

Combines vector search with graph traversal to include:
- Related people (who reacted/commented/created)
- Original posts (for reposts)
- Graph context

Better for queries requiring relationship context.

## Example Queries

- "What posts did I like about machine learning?"
- "Summarize the topics in posts I commented on"
- "What are people discussing in posts I reacted to?"
- "Find posts about AI that I engaged with"

## Troubleshooting

### No content extracted

LinkedIn pages may require authentication or have dynamic content. The script uses basic HTML parsing which may not work for all posts.

### Embedding errors

Ensure Google Cloud credentials are properly configured:
```bash
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/credentials.json
```

Or use Application Default Credentials:
```bash
gcloud auth application-default login
```

### Vector index errors

The script automatically creates the vector index if it doesn't exist. If you encounter errors:
1. Check Neo4j APOC is installed (required for some operations)
2. Verify embedding dimensions match (768 for textembedding-gecko@002)

### Embedding model errors

If you get a "model not found" error:
- The script uses `textembedding-gecko@002` by default (lightweight, stable)
- Alternative models: `textembedding-gecko` (latest), `textembedding-gecko@001`
- The script will fail immediately if embedding generation fails (fail-fast behavior)
- Verify the model is available in your Vertex AI project

## Next Steps

- **User Profile Indexing**: Extend to index user profile content (requires API access)
- **Custom Chunking**: Adjust chunk size/overlap for your use case
- **Hybrid Retrieval**: Add full-text search for better recall
- **Text2Cypher**: Use natural language to Cypher query conversion

## Architecture

```
Post/Comment (with URL)
    ↓
Extract HTML content
    ↓
Split into chunks
    ↓
Generate embeddings
    ↓
Create Chunk nodes
    ↓
Link: Chunk -[:FROM_CHUNK]-> Post/Comment
    ↓
Vector Index (for fast retrieval)
    ↓
GraphRAG Query
```

## Files

- `index_content.py` - Content extraction and indexing
- `query_graphrag.py` - GraphRAG query interface
- `build_graph.py` - Load graph data into Neo4j (run first)
