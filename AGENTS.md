# AGENTS.md

## Cursor Cloud specific instructions

### Overview

Python client for LinkedIn's Portability API — fetches activity, builds a Neo4j knowledge graph, and provides GraphRAG semantic search via a Gradio UI. See `CLAUDE.md` for full architecture and command reference.

### Running services

- **Gradio app**: `uv run python -m linkedin_api.gradio_app` (port 7860). The UI starts without Neo4j/LLM but full pipeline requires both.
- **Neo4j**: Required for graph operations. Not included in the repo — must be provisioned externally or via Docker. Default URI: `neo4j://localhost:7687`.
- **LLM/Embedder**: Required for enrichment, indexing, and queries. Falls back to Ollama if no API key is set.
- **Ollama**: Pre-installed with `llama3.2:3b` and `nomic-embed-text` models. In non-systemd environments (like this VM), start with `ollama serve &` before using LLM/embedding features. The `neo4j-graphrag[ollama]` extra is included in dependencies.

### Development commands

All commands use `uv run` as the project manages dependencies with `uv`. See `CLAUDE.md` for the full list.

| Task | Command |
|------|---------|
| Install deps | `uv sync --all-groups` |
| Tests | `uv run pytest` |
| Format check | `uv run black --check .` |
| Lint | `uv run flake8 linkedin_api tests examples *.py` |
| Type check | `uv run mypy linkedin_api` (non-blocking; pre-existing errors) |
| Gradio app | `uv run python -m linkedin_api.gradio_app` |

### Gotchas

- **mypy must pass clean** (`uv run mypy linkedin_api`). All three linters (`black`, `flake8`, `mypy`) must pass before committing.
- **`uv` must be on PATH**: install with `curl -LsSf https://astral.sh/uv/install.sh | sh` and ensure `$HOME/.local/bin` is on PATH.
- **Commits**: Use conventional commits with gitmoji (see `CLAUDE.md`).
- **Python 3.12+** is required (`requires-python = ">=3.12"` in `pyproject.toml`).
- **zstd** is pre-installed as a system dependency (used by Ollama for model compression).
- **Ollama serve must be started manually** in this VM since there is no systemd. Run `ollama serve &` and wait a few seconds before any LLM/embedding operations. The app's `_ensure_ollama_running()` in `llm_config.py` will also attempt auto-start.
