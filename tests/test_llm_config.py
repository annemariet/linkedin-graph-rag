"""Tests for llm_config module (import, config parsing, key resolution)."""

import sys

import pytest

from linkedin_api.llm_config import _resolve_anthropic_api_key, _resolve_api_key


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


class TestResolveApiKey:
    def test_llm_api_key_env_var(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "sk-test-123")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        key, source = _resolve_api_key(quiet=True)
        assert key == "sk-test-123"
        assert "LLM_API_KEY" in source

    def test_openai_api_key_fallback(self, monkeypatch):
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-456")
        # Mock keyring to return None so we fall through to OPENAI_API_KEY
        import linkedin_api.llm_config as mod

        monkeypatch.setattr(mod, "_KEYRING_SERVICE", "__test_nonexistent__")
        key, source = _resolve_api_key(quiet=True)
        assert key == "sk-openai-456"
        assert "OPENAI_API_KEY" in source

    def test_no_key_returns_none(self, monkeypatch):
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        import linkedin_api.llm_config as mod

        monkeypatch.setattr(mod, "_KEYRING_SERVICE", "__test_nonexistent__")
        key, source = _resolve_api_key(quiet=True)
        assert key is None
        assert source is None

    def test_llm_api_key_takes_priority_over_openai(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "sk-llm")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
        key, _ = _resolve_api_key(quiet=True)
        assert key == "sk-llm"


class TestResolveAnthropicApiKey:
    def test_anthropic_api_key_env_var(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-123")
        key, source = _resolve_anthropic_api_key(quiet=True)
        assert key == "sk-ant-123"
        assert "ANTHROPIC_API_KEY" in source

    def test_anthropic_keyring_lookup(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        import linkedin_api.llm_config as mod

        monkeypatch.setattr(mod, "_ANTHROPIC_KEYRING_LOOKUPS", (("svc", "acct"),))

        class DummyKeyring:
            @staticmethod
            def get_password(service, account):
                if service == "svc" and account == "acct":
                    return "sk-ant-keyring"
                return None

        monkeypatch.setitem(sys.modules, "keyring", DummyKeyring())

        key, source = _resolve_anthropic_api_key(quiet=True)
        assert key == "sk-ant-keyring"
        assert "svc/acct" in source


def test_create_llm_anthropic_defaults(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-xyz")
    monkeypatch.delenv("LLM_MODEL", raising=False)

    class DummyAnthropicLLM:
        def __init__(self, model_name, model_params=None, **kwargs):
            self.model_name = model_name
            self.model_params = model_params
            self.kwargs = kwargs

    import neo4j_graphrag.llm as llm_module

    monkeypatch.setattr(llm_module, "AnthropicLLM", DummyAnthropicLLM)

    from linkedin_api.llm_config import create_llm

    llm = create_llm(quiet=True)
    assert isinstance(llm, DummyAnthropicLLM)
    assert llm.model_name == "claude-sonnet-4-5"
    assert llm.model_params == {"temperature": 0}
    assert llm.kwargs["api_key"] == "sk-ant-xyz"
