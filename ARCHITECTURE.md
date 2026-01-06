# Architecture Overview

> **Note**: This architecture documentation is also included in [CLAUDE.md](CLAUDE.md) for developer convenience. CLAUDE.md is the comprehensive guide for Claude Code and includes all commands, workflows, and design patterns.

## Module Structure

### Core Scripts (CLI + Module)

All core scripts can be used both as:
- **CLI tools** (run directly with `uv run python -m`)
- **Importable modules** (used by other scripts)

#### `linkedin_api/query_graphrag.py`

**CLI Usage:**
```bash
uv run python -m linkedin_api.query_graphrag "What are my main themes?"
uv run python -m linkedin_api.query_graphrag  # Interactive mode
```

**Module Usage:**
```python
from linkedin_api.query_graphrag import (
    find_vector_index,
    create_vector_retriever,
    create_vector_cypher_retriever,
    NEO4J_URI,
    EMBEDDING_MODEL,
    # ... other constants
)
```

**Exports:**
- `find_vector_index()` - Locate vector indexes in Neo4j
- `create_vector_retriever()` - Create basic vector retriever
- `create_vector_cypher_retriever()` - Create graph-traversal retriever
- `query_graphrag()` - Query GraphRAG system
- Configuration constants (NEO4J_URI, etc.)

#### `linkedin_api/index_content.py`

**CLI Usage:**
```bash
uv run python -m linkedin_api.index_content
uv run python -m linkedin_api.index_content --limit 5
```

**Module Usage:**
```python
from linkedin_api.index_content import (
    extract_post_content,
    split_text_into_chunks,
    index_content_for_graphrag,
    # ... configuration constants
)
```

**Exports:**
- `extract_post_content()` - Extract text from LinkedIn URLs
- `split_text_into_chunks()` - Text chunking with overlap
- `index_content_for_graphrag()` - Main indexing function
- Configuration constants

### Web Application

#### `linkedin_api/gradio_app.py`

**Usage:**
```bash
uv run python -m linkedin_api.gradio_app
# or via Procfile on Scalingo
```

**Architecture:**
- **No code duplication** - Imports functions from `query_graphrag.py`
- **Cloud-ready** - Handles GCP credentials from env vars
- **Port-aware** - Respects `$PORT` for Scalingo deployment

**Imports:**
```python
from linkedin_api.query_graphrag import (
    find_vector_index,
    create_vector_retriever,
    create_vector_cypher_retriever,
    NEO4J_URI,
    # ... all configuration
)
```

## Deployment Files

### `Procfile`
```
web: uv run python -m linkedin_api.gradio_app
```

For Scalingo (if uv not available):
```
web: python -m linkedin_api.gradio_app
```

### `requirements.txt`
- Generated from `pyproject.toml`
- Includes all dependencies + Gradio
- Compatible with Scalingo Python buildpack

### `runtime.txt`
```
python-3.12.0
```

## Benefits of This Architecture

1. **No Code Duplication**
   - Gradio app imports from existing modules
   - Single source of truth for business logic

2. **Modular Design**
   - Each script can be used standalone or imported
   - Clean separation of concerns

3. **Deployment Ready**
   - Proper guards around `__main__` blocks
   - No side effects on import
   - Cloud credentials handling

4. **Maintainable**
   - Changes to query logic automatically reflected in web UI
   - Configuration in one place
   - Clear module boundaries

## File Dependencies

```
gradio_app.py
  ├── query_graphrag.py (imports functions + config)
  └── neo4j, neo4j_graphrag, gradio (libraries)

query_graphrag.py
  └── neo4j, neo4j_graphrag (libraries)

index_content.py
  └── neo4j, neo4j_graphrag, beautifulsoup4 (libraries)
```

## Best Practices Applied

✅ **Guard main execution** - All scripts use `if __name__ == "__main__":`
✅ **Import from modules** - No code duplication
✅ **Export constants** - Configuration available to importers
✅ **Clean entry points** - `main()` functions for CLI usage
✅ **Type hints** - Functions have proper signatures
✅ **Docstrings** - All exports documented
✅ **Cloud-ready** - GCP credentials handling for deployment
