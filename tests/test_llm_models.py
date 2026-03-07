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


def test_fetch_all_provider_models_returns_all_keys():
    from linkedin_api.llm_models import fetch_all_provider_models

    result = fetch_all_provider_models()
    assert set(result.keys()) == {"ollama", "anthropic", "mammouth"}
    for v in result.values():
        assert isinstance(v, list)


def test_fetch_mammouth_models_failure():
    """When /public/models request fails, return []."""
    with patch("urllib.request.urlopen", side_effect=OSError("network unreachable")):
        result = fetch_mammouth_models()
    assert result == []


def test_fetch_mammouth_models_success():
    """Mammouth returns list of (label, id) with owner and cost per M."""
    mock_resp = {
        "data": [
            {
                "id": "gpt-4o",
                "owned_by": "openai",
                "model_info": {
                    "input_cost_per_token": 2.5e-06,
                    "output_cost_per_token": 1e-05,
                },
            },
            {"id": "no-cost", "owned_by": "other"},
        ]
    }
    with patch("urllib.request.urlopen") as m:
        m.return_value.__enter__.return_value.read.return_value = json.dumps(
            mock_resp
        ).encode()
        result = fetch_mammouth_models()
    assert len(result) == 2
    # Sorted by input cost: no-cost (0) first, then gpt-4o (2.5/M)
    assert result[0][1] == "no-cost"
    assert result[0] == ("no-cost · other", "no-cost")
    assert result[1][1] == "gpt-4o"
    assert "OpenAI" in result[1][0]
    assert "2.50" in result[1][0] and "10.00" in result[1][0]
