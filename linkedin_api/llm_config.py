"""
Configurable LLM and embedder factory.

Supports OpenAI-compatible (including Mammouth), Ollama, and VertexAI providers.

API key resolution order (for OpenAI-compatible providers):
1. ``LLM_API_KEY`` environment variable
2. macOS Keychain: ``keyring.get_password("agent-fleet-rts", "mammouth_api_key")``
3. ``OPENAI_API_KEY`` environment variable
4. If none found: automatic fallback to Ollama

When using Mammouth/OpenAI: rate limits (429) are retried with 1s delay; budget
errors (400, quota exceeded) trigger fallback to Ollama.

Environment variables:

  LLM_PROVIDER        openai | ollama | vertexai   (default: openai)
  LLM_MODEL           Model name                   (default: gpt-4o)
  LLM_BASE_URL        Custom base URL               (default: https://api.mammouth.ai/v1)
  LLM_API_KEY         API key (for OpenAI-compatible providers)
  EMBEDDING_PROVIDER   openai | ollama | vertexai   (default: openai)
  EMBEDDING_MODEL      Embedding model name         (default: text-embedding-ada-002)
  OLLAMA_BASE_URL      Ollama server URL            (default: http://localhost:11434)
"""

import os
import subprocess
import time
import warnings

MAMMOUTH_BASE_URL = "https://api.mammouth.ai/v1"
OLLAMA_DEFAULT_URL = "http://localhost:11434"

# Keyring service/account matching agent-fleet-rts manage_keys.py convention:
#   uv run backend/src/scripts/manage_keys.py set mammouth_api_key
_KEYRING_SERVICE = "agent-fleet-rts"
_KEYRING_ACCOUNT = "mammouth_api_key"


def _resolve_api_key(quiet=False):
    """Try to find an OpenAI-compatible API key.

    Returns (api_key, source_description) or (None, None).
    """
    # 1. Explicit env var
    key = os.getenv("LLM_API_KEY")
    if key:
        if not quiet:
            print("  Using API key from LLM_API_KEY env var")
        return key, "LLM_API_KEY env var"

    # 2. macOS Keychain (Mammouth)
    #    Store with: uv run backend/src/scripts/manage_keys.py set mammouth_api_key  (from agent-fleet-rts)
    try:
        import keyring

        key = keyring.get_password(_KEYRING_SERVICE, _KEYRING_ACCOUNT)
        if key:
            if not quiet:
                print(
                    f"  Using Mammouth API key from keyring "
                    f"(service={_KEYRING_SERVICE!r}, account={_KEYRING_ACCOUNT!r})"
                )
            return key, "macOS Keychain (agent-fleet-rts/mammouth_api_key)"
    except Exception as exc:
        if not quiet:
            warnings.warn(f"Keyring lookup failed: {exc}", stacklevel=3)

    # 3. OPENAI_API_KEY env var (standard OpenAI SDK default)
    key = os.getenv("OPENAI_API_KEY")
    if key:
        if not quiet:
            print("  Using API key from OPENAI_API_KEY env var")
        return key, "OPENAI_API_KEY env var"

    return None, None


def _ensure_ollama_running(base_url=None):
    """Start Ollama server if it's not already running. Returns True if reachable."""
    import urllib.request
    import urllib.error

    url = base_url or OLLAMA_DEFAULT_URL
    # Check if already running
    try:
        req = urllib.request.Request(url, method="GET")
        urllib.request.urlopen(req, timeout=2)
        return True
    except (urllib.error.URLError, OSError):
        pass

    # Try to start it
    print("  Starting Ollama server...")
    try:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        print("  Ollama is not installed. Install it from https://ollama.com")
        return False

    # Wait for it to come up
    for _ in range(10):
        time.sleep(1)
        try:
            req = urllib.request.Request(url, method="GET")
            urllib.request.urlopen(req, timeout=2)
            print("  Ollama server started successfully")
            return True
        except (urllib.error.URLError, OSError):
            continue

    print("  Ollama server did not start in time")
    return False


def _is_rate_limit(exc: BaseException) -> bool:
    """True if error is rate limit (429) — retry with delay."""
    msg = str(exc).lower()
    if any(x in msg for x in ("429", "rate limit", "too many requests")):
        return True
    if getattr(exc, "status_code", None) == 429:
        return True
    if hasattr(exc, "response") and exc.response is not None:
        return getattr(exc.response, "status_code", None) == 429
    return False


def _is_budget_error(exc: BaseException) -> bool:
    """True if error suggests budget/quota exhausted — fallback to Ollama."""
    msg = str(exc).lower()
    if any(x in msg for x in ("400", "bad request", "quota", "budget", "exceeded")):
        return True
    if getattr(exc, "status_code", None) in (400, 402):
        return True
    if hasattr(exc, "response") and exc.response is not None:
        return getattr(exc.response, "status_code", None) in (400, 402)
    return False


class _FallbackLLM:
    """Wraps primary LLM: retries on rate limit, falls back to Ollama on budget errors."""

    def __init__(self, primary, quiet=False):
        self._primary = primary
        self._quiet = quiet
        self._fallback_llm = None
        self._budget_exhausted = False

    def _get_fallback(self):
        if self._fallback_llm is None:
            if not self._quiet:
                print("  API budget exceeded, falling back to Ollama...")
            self._fallback_llm = _create_ollama_llm(quiet=self._quiet, is_fallback=True)
        return self._fallback_llm

    def invoke(self, input: str, message_history=None, system_instruction=None):
        if self._budget_exhausted:
            return self._get_fallback().invoke(
                input,
                message_history=message_history,
                system_instruction=system_instruction,
            )

        last_exc = None
        for attempt in range(4):  # 1 initial + 3 retries for rate limit
            try:
                return self._primary.invoke(
                    input,
                    message_history=message_history,
                    system_instruction=system_instruction,
                )
            except Exception as e:
                last_exc = e
                if _is_rate_limit(e) and attempt < 3:
                    if not self._quiet:
                        print("  Rate limited, retrying in 1s...")
                    time.sleep(1)
                    continue
                if _is_budget_error(e):
                    self._budget_exhausted = True
                if _is_budget_error(e) or (_is_rate_limit(e) and attempt >= 3):
                    fallback = self._get_fallback()
                    return fallback.invoke(
                        input,
                        message_history=message_history,
                        system_instruction=system_instruction,
                    )
                raise
        raise last_exc

    def __getattr__(self, name):
        return getattr(self._primary, name)


def create_llm(quiet=False, json_mode=True):
    """Create LLM instance based on LLM_PROVIDER env var.

    If provider is ``openai`` but no API key is found, falls back to Ollama
    automatically (starting the server if needed).

    Args:
        quiet: Suppress log output.
        json_mode: If True (default), set response_format to json_object for JSON
            output (e.g. summarize_posts). If False, no response_format so the LLM
            can return plain text (e.g. report generation). Some providers (e.g.
            Mammouth) require the prompt to mention "json" when json_mode is True.
    """
    provider = os.getenv("LLM_PROVIDER", "openai")

    if provider == "openai":
        api_key, source = _resolve_api_key(quiet=quiet)

        if not api_key:
            print(
                "  No OpenAI-compatible API key found. Tried:\n"
                "    1. LLM_API_KEY env var\n"
                "    2. macOS Keychain (agent-fleet-rts / mammouth_api_key)\n"
                "    3. OPENAI_API_KEY env var\n"
                "  Falling back to Ollama..."
            )
            return _create_ollama_llm(quiet=quiet, is_fallback=True)

        base_url = os.getenv("LLM_BASE_URL", MAMMOUTH_BASE_URL)
        model = os.getenv("LLM_MODEL", "gpt-4o")
        # Mammouth uses its own model IDs; raw Gemini names (e.g. gemini-2.5-flash-lite) often fail
        if MAMMOUTH_BASE_URL in (base_url or "").split("?")[0] and model.startswith(
            "gemini-2.5"
        ):
            if not quiet:
                warnings.warn(
                    f"LLM_MODEL={model!r} may be invalid for Mammouth. "
                    "Using gpt-4o. Set LLM_MODEL to a model from GET /v1/models if needed.",
                    stacklevel=2,
                )
            model = "gpt-4o"

        from neo4j_graphrag.llm import OpenAILLM

        if not quiet:
            print(f"  LLM: OpenAI-compatible ({model} via {base_url})")

        model_params = {"temperature": 0}
        if json_mode:
            model_params["response_format"] = {"type": "json_object"}
        primary = OpenAILLM(
            model_name=model,
            model_params=model_params,
            api_key=api_key,
            base_url=base_url,
        )
        return _FallbackLLM(primary, quiet=quiet)
    elif provider == "ollama":
        return _create_ollama_llm(quiet=quiet)
    elif provider == "vertexai":
        from neo4j_graphrag.llm import VertexAILLM

        if not quiet:
            print(f"  LLM: VertexAI ({os.getenv('LLM_MODEL', 'gemini-1.5-pro')})")
        return VertexAILLM(
            model_name=os.getenv("LLM_MODEL", "gemini-1.5-pro"),
        )
    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {provider!r}")


OLLAMA_DEFAULT_LLM_MODEL = "llama3.2:3b"
OLLAMA_DEFAULT_EMBEDDING_MODEL = "nomic-embed-text"


def _create_ollama_llm(quiet=False, is_fallback=False):
    """Create an Ollama LLM, starting the server if needed."""
    base_url = os.getenv("OLLAMA_BASE_URL", OLLAMA_DEFAULT_URL)
    # When falling back from OpenAI, ignore LLM_MODEL (e.g. "gpt-4o") — use Ollama default
    model = (
        OLLAMA_DEFAULT_LLM_MODEL
        if is_fallback
        else os.getenv("LLM_MODEL", OLLAMA_DEFAULT_LLM_MODEL)
    )

    if not _ensure_ollama_running(base_url):
        raise RuntimeError(
            "Cannot connect to Ollama. Install from https://ollama.com "
            "or set LLM_API_KEY / MAMMOUTH_API_KEY in keyring."
        )

    from neo4j_graphrag.llm import OllamaLLM

    if not quiet:
        print(f"  LLM: Ollama ({model} at {base_url})")

    # Use `host=` not `base_url=` — ollama.Client expects `host` and
    # passes **kwargs through to httpx.Client which already gets base_url.
    return OllamaLLM(model_name=model, host=base_url)


def create_embedder(quiet=False):
    """Create embedder instance based on EMBEDDING_PROVIDER env var.

    Falls back to Ollama if no API key is available for OpenAI-compatible providers.
    """
    provider = os.getenv("EMBEDDING_PROVIDER", "openai")

    if provider == "openai":
        api_key, source = _resolve_api_key(quiet=True)

        if not api_key:
            if not quiet:
                print("  No API key for embeddings, falling back to Ollama embedder")
            return _create_ollama_embedder(quiet=quiet, is_fallback=True)

        base_url = os.getenv("LLM_BASE_URL", MAMMOUTH_BASE_URL)

        from neo4j_graphrag.embeddings.openai import OpenAIEmbeddings

        model = os.getenv("EMBEDDING_MODEL", "text-embedding-ada-002")
        if not quiet:
            print(f"  Embedder: OpenAI-compatible ({model} via {base_url})")

        return OpenAIEmbeddings(model=model, api_key=api_key, base_url=base_url)
    elif provider == "ollama":
        return _create_ollama_embedder(quiet=quiet)
    elif provider == "vertexai":
        from neo4j_graphrag.embeddings.vertexai import VertexAIEmbeddings

        model = os.getenv("EMBEDDING_MODEL", "textembedding-gecko@002")
        if not quiet:
            print(f"  Embedder: VertexAI ({model})")
        return VertexAIEmbeddings(model=model)
    else:
        raise ValueError(f"Unknown EMBEDDING_PROVIDER: {provider!r}")


def _create_ollama_embedder(quiet=False, is_fallback=False):
    """Create an Ollama embedder, starting the server if needed."""
    base_url = os.getenv("OLLAMA_BASE_URL", OLLAMA_DEFAULT_URL)
    # When falling back from OpenAI, ignore EMBEDDING_MODEL (e.g. "gemini-embedding-001")
    model = (
        OLLAMA_DEFAULT_EMBEDDING_MODEL
        if is_fallback
        else os.getenv("EMBEDDING_MODEL", OLLAMA_DEFAULT_EMBEDDING_MODEL)
    )

    if not _ensure_ollama_running(base_url):
        raise RuntimeError(
            "Cannot connect to Ollama for embeddings. Install from https://ollama.com "
            "or set LLM_API_KEY / MAMMOUTH_API_KEY in keyring."
        )

    from neo4j_graphrag.embeddings import OllamaEmbeddings

    if not quiet:
        print(f"  Embedder: Ollama ({model} at {base_url})")

    # Use `host=` not `base_url=` — same ollama.Client bug as LLM above.
    return OllamaEmbeddings(model=model, host=base_url)
