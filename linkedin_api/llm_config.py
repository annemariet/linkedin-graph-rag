"""
Configurable LLM and embedder factory.

Supports OpenAI-compatible (including Mammouth), Ollama, and VertexAI providers.
Configuration is via environment variables:

  LLM_PROVIDER        openai | ollama | vertexai   (default: openai)
  LLM_MODEL           Model name                   (default: gpt-4o)
  LLM_BASE_URL        Custom base URL for OpenAI-compatible APIs
  LLM_API_KEY         API key (for OpenAI-compatible providers)
  EMBEDDING_PROVIDER   openai | ollama | vertexai   (default: openai)
  EMBEDDING_MODEL      Embedding model name         (default: text-embedding-ada-002)
  OLLAMA_BASE_URL      Ollama server URL            (default: http://localhost:11434)
"""

import os


def create_llm():
    """Create LLM instance based on LLM_PROVIDER env var."""
    provider = os.getenv("LLM_PROVIDER", "openai")

    if provider == "openai":
        from neo4j_graphrag.llm import OpenAILLM

        return OpenAILLM(
            model_name=os.getenv("LLM_MODEL", "gpt-4o"),
            model_params={
                "temperature": 0,
                "response_format": {"type": "json_object"},
            },
            api_key=os.getenv("LLM_API_KEY"),
            base_url=os.getenv("LLM_BASE_URL"),
        )
    elif provider == "ollama":
        from neo4j_graphrag.llm import OllamaLLM

        return OllamaLLM(
            model_name=os.getenv("LLM_MODEL", "llama3"),
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        )
    elif provider == "vertexai":
        from neo4j_graphrag.llm import VertexAILLM

        return VertexAILLM(
            model_name=os.getenv("LLM_MODEL", "gemini-1.5-pro"),
        )
    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {provider!r}")


def create_embedder():
    """Create embedder instance based on EMBEDDING_PROVIDER env var."""
    provider = os.getenv("EMBEDDING_PROVIDER", "openai")

    if provider == "openai":
        from neo4j_graphrag.embeddings.openai import OpenAIEmbeddings

        kwargs = {
            "model": os.getenv("EMBEDDING_MODEL", "text-embedding-ada-002"),
        }
        api_key = os.getenv("LLM_API_KEY")
        if api_key:
            kwargs["api_key"] = api_key
        base_url = os.getenv("LLM_BASE_URL")
        if base_url:
            kwargs["base_url"] = base_url
        return OpenAIEmbeddings(**kwargs)
    elif provider == "ollama":
        from neo4j_graphrag.embeddings import OllamaEmbeddings

        return OllamaEmbeddings(
            model=os.getenv("EMBEDDING_MODEL", "nomic-embed-text"),
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        )
    elif provider == "vertexai":
        from neo4j_graphrag.embeddings.vertexai import VertexAIEmbeddings

        return VertexAIEmbeddings(
            model=os.getenv("EMBEDDING_MODEL", "textembedding-gecko@002"),
        )
    else:
        raise ValueError(f"Unknown EMBEDDING_PROVIDER: {provider!r}")
