"""
Fetch available models from LLM providers for UI selection.

Supports Ollama (local), Anthropic API, Mammouth API (OpenAI-compatible).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from linkedin_api.llm_config import (
    MAMMOUTH_BASE_URL,
    OLLAMA_DEFAULT_URL,
    _resolve_api_key,
    _resolve_anthropic_api_key,
)


def fetch_ollama_models(base_url: str | None = None) -> list[str]:
    """List models available in Ollama. Returns model names."""
    url = (base_url or OLLAMA_DEFAULT_URL).rstrip("/") + "/api/tags"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
        models = data.get("models", [])
        return [m.get("name", "") for m in models if m.get("name")]
    except (urllib.error.URLError, OSError, json.JSONDecodeError, KeyError):
        return []


def fetch_anthropic_models() -> list[str]:
    """List models from Anthropic API. Requires ANTHROPIC_API_KEY."""
    api_key, _ = _resolve_anthropic_api_key(quiet=True)
    if not api_key:
        return []
    url = "https://api.anthropic.com/v1/models"
    try:
        req = urllib.request.Request(
            url,
            method="GET",
            headers={
                "anthropic-version": "2023-06-01",
                "x-api-key": api_key,
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        items = data.get("data", [])
        return [m.get("id", "") for m in items if m.get("id")]
    except (urllib.error.URLError, OSError, json.JSONDecodeError, KeyError):
        return []


def fetch_mammouth_models() -> list[str]:
    """List models from Mammouth API (OpenAI-compatible). Requires LLM_API_KEY."""
    api_key, _ = _resolve_api_key(quiet=True)
    if not api_key:
        return []
    base_url = os.getenv("LLM_BASE_URL", MAMMOUTH_BASE_URL).rstrip("/")
    url = base_url + "/v1/models"
    try:
        req = urllib.request.Request(
            url,
            method="GET",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        items = data.get("data", [])
        return [m.get("id", "") for m in items if m.get("id")]
    except (urllib.error.URLError, OSError, json.JSONDecodeError, KeyError):
        return []


def fetch_models_for_provider(provider: str) -> list[str]:
    """Fetch model list for the given provider. Returns empty list on error."""
    if provider == "ollama":
        return fetch_ollama_models()
    if provider == "anthropic":
        return fetch_anthropic_models()
    if provider == "mammouth":
        return fetch_mammouth_models()
    return []
