"""Tests for llm_models module."""

import json
from unittest.mock import patch

from linkedin_api.llm_models import (
    fetch_anthropic_models,
    fetch_models_for_provider,
    fetch_ollama_models,
    fetch_mammouth_models,
)


def test_fetch_models_for_provider_unknown():
    assert fetch_models_for_provider("unknown") == []


def test_fetch_ollama_models_success():
    mock_resp = {"models": [{"name": "llama3.2:3b"}, {"name": "nomic-embed-text"}]}
    with patch("urllib.request.urlopen") as m:
        m.return_value.__enter__.return_value.read.return_value = json.dumps(
            mock_resp
        ).encode()
        result = fetch_ollama_models()
    assert result == ["llama3.2:3b", "nomic-embed-text"]


def test_fetch_ollama_models_empty():
    with patch("urllib.request.urlopen") as m:
        m.return_value.__enter__.return_value.read.return_value = json.dumps(
            {"models": []}
        ).encode()
        result = fetch_ollama_models()
    assert result == []


def test_fetch_anthropic_models_no_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with patch(
        "linkedin_api.llm_models._resolve_anthropic_api_key", return_value=(None, None)
    ):
        result = fetch_anthropic_models()
    assert result == []


def test_fetch_mammouth_models_no_key(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with patch("linkedin_api.llm_models._resolve_api_key", return_value=(None, None)):
        result = fetch_mammouth_models()
    assert result == []
