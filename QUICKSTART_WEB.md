# Quick Start: Gradio Web Interface

## Run Locally

Test the Gradio web interface before deploying:

```bash
# Install dependencies (if not already)
uv sync

# Set environment variables in .env file
cp .env.example .env
# Edit .env with your Neo4j and GCP credentials

# Run the web app
uv run python -m linkedin_api.gradio_app
```

Visit `http://localhost:7860` in your browser.

**Development:** Auto-reload is a Gradio **CLI** feature (there is no `watch` argument in `launch()`). Run `uv run gradio linkedin_api/gradio_app.py` and pass `--demo-name` if your demo variable has another name. Our app builds the demo in `main()`, so to use CLI reload you’d need a module-level `demo`; until then, restart the process to pick up code changes.

## Features

- **Natural language queries** - Ask questions about your LinkedIn content
- **Vector search** - Fast semantic search through indexed posts/comments
- **Graph traversal** - Optional Cypher mode to include related entities
- **Database stats** - Real-time view of indexed content
- **Example queries** - Get started quickly with pre-made queries

## UI Components

- **Query input** - Enter your natural language question
- **Graph Traversal toggle** - Enable to use VectorCypherRetriever (includes relationships)
- **Top K slider** - Control number of results (1-20)
- **Database stats** - Monitor chunks, posts, comments
- **Example queries** - Click to try sample questions

## Configuration

> **Note**: For complete environment variable documentation, see [CLAUDE.md](CLAUDE.md#environment-variables).

Edit environment variables:

```bash
# Neo4j
NEO4J_URI=neo4j://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your-password
NEO4J_DATABASE=neo4j

# Vertex AI
EMBEDDING_MODEL=textembedding-gecko@002
LLM_MODEL=gemini-1.5-pro
VECTOR_INDEX_NAME=linkedin_content_index

# Google Cloud (one of these)
GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json
# OR for cloud deployment:
GOOGLE_APPLICATION_CREDENTIALS_JSON='{"type": "service_account", ...}'
```

## Deploy to Scalingo

See [SCALINGO_DEPLOYMENT.md](SCALINGO_DEPLOYMENT.md) for full instructions.

Quick version:

```bash
# If Scalingo doesn't support uv, use standard Procfile
cp Procfile.standard Procfile

scalingo create my-app
scalingo --app my-app env-set NEO4J_URI="..." NEO4J_PASSWORD="..."
# Set other env vars...
git push scalingo main
```

## Tips

- **First time?** Ensure you've run `index_content.py` to create the vector index
- **No results?** Check database stats - you need chunks with embeddings
- **Slow queries?** Try reducing top_k or use faster models
- **Better answers?** Enable Graph Traversal for context-rich queries

## Example Queries

Try these:

- "What are the main themes in my LinkedIn posts?"
- "Show me posts about AI or machine learning"
- "Who comments most frequently on my posts?" (enable Graph Traversal)
- "What questions do people ask in my comments?"
