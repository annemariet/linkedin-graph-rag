"""Tests for llm_config module (import and config parsing only)."""

import pytest


def test_create_llm_unknown_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "unknown_provider")
    from linkedin_api.llm_config import create_llm

    with pytest.raises(ValueError, match="Unknown LLM_PROVIDER"):
        create_llm()


def test_create_embedder_unknown_provider(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "unknown_provider")
    from linkedin_api.llm_config import create_embedder

    with pytest.raises(ValueError, match="Unknown EMBEDDING_PROVIDER"):
        create_embedder()


def test_module_importable():
    from linkedin_api.llm_config import create_llm, create_embedder  # noqa: F401
