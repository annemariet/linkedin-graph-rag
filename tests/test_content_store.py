"""Tests for content_store module -- file-based content storage."""

import pytest

from linkedin_api.content_store import (
    content_path,
    has_content,
    load_content,
    save_content,
)


@pytest.fixture(autouse=True)
def use_tmp_data_dir(monkeypatch, tmp_path):
    """Point the content store at a temp directory for all tests."""
    monkeypatch.setenv("LINKEDIN_DATA_DIR", str(tmp_path))


class TestSaveAndLoad:
    def test_roundtrip(self):
        urn = "urn:li:ugcPost:123456"
        save_content(urn, "Hello world")
        assert load_content(urn) == "Hello world"

    def test_overwrite(self):
        urn = "urn:li:ugcPost:123456"
        save_content(urn, "v1")
        save_content(urn, "v2")
        assert load_content(urn) == "v2"

    def test_unicode_content(self):
        urn = "urn:li:ugcPost:999"
        text = "Inscrite ! Merci pour l'info \U0001f44d\U0001f3fb"
        save_content(urn, text)
        assert load_content(urn) == text

    def test_multiline_content(self):
        urn = "urn:li:ugcPost:888"
        text = "Line 1\nLine 2\n\nLine 4"
        save_content(urn, text)
        assert load_content(urn) == text

    def test_save_empty_urn_raises(self):
        with pytest.raises(ValueError):
            save_content("", "some text")

    def test_save_empty_text_raises(self):
        with pytest.raises(ValueError):
            save_content("urn:li:ugcPost:1", "")


class TestLoadContent:
    def test_missing_urn_returns_none(self):
        assert load_content("urn:li:ugcPost:nonexistent") is None

    def test_empty_urn_returns_none(self):
        assert load_content("") is None


class TestHasContent:
    def test_exists_after_save(self):
        urn = "urn:li:ugcPost:777"
        assert has_content(urn) is False
        save_content(urn, "stored")
        assert has_content(urn) is True

    def test_empty_urn(self):
        assert has_content("") is False


class TestContentPath:
    def test_returns_path(self):
        path = content_path("urn:li:ugcPost:123")
        assert path.suffix == ".md"
        assert "content" in str(path)

    def test_different_urns_different_paths(self):
        p1 = content_path("urn:li:ugcPost:111")
        p2 = content_path("urn:li:ugcPost:222")
        assert p1 != p2
