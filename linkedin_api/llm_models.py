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
    _ensure_ollama_running,
    _resolve_anthropic_api_key,
)


def fetch_ollama_models(base_url: str | None = None) -> list[str]:
    """List models available in Ollama. Returns model names. Starts Ollama if needed."""
    base = base_url or OLLAMA_DEFAULT_URL
    if not _ensure_ollama_running(base):
        return []
    url = base.rstrip("/") + "/api/tags"
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
    """List models from Mammouth API GET /public/models (no auth)."""
    base = os.getenv("LLM_BASE_URL", MAMMOUTH_BASE_URL).rstrip("/")
    api_root = base.removesuffix("/v1") if base.endswith("/v1") else base
    url = f"{api_root}/public/models"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        items = data.get("data", data.get("models", data.get("list", [])))
        if not isinstance(items, list) or not items:
            return []
        return [
            str(m.get("id") or m.get("model_id") or m.get("name", ""))
            for m in items
            if isinstance(m, dict)
            and (m.get("id") or m.get("model_id") or m.get("name"))
        ]
    except (
        urllib.error.URLError,
        OSError,
        urllib.error.HTTPError,
        json.JSONDecodeError,
        KeyError,
    ):
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


def fetch_all_provider_models() -> dict[str, list[str]]:
    """Fetch models for all providers in parallel. Returns {provider: [models]}."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    providers = ["ollama", "anthropic", "mammouth"]
    result: dict[str, list[str]] = {}

    with ThreadPoolExecutor(max_workers=3) as ex:
        futures = {ex.submit(fetch_models_for_provider, p): p for p in providers}
        for fut in as_completed(futures):
            provider = futures[fut]
            try:
                models = fut.result()
                result[provider] = models if models else []
            except Exception:
                result[provider] = []
    return result
