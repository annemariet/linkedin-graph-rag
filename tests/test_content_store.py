"""Tests for content_store module -- file-based content storage."""

import pytest

from linkedin_api.content_store import (
    content_path,
    has_content,
    load_content,
    load_metadata,
    list_posts_needing_summary,
    needs_summary,
    save_content,
    save_metadata,
    update_summary_metadata,
    update_urls_metadata,
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


class TestMetadata:
    def test_save_and_load_metadata(self):
        urn = "urn:li:ugcPost:456"
        save_content(urn, "Content here")
        save_metadata(
            urn, summary="A summary", topics=["AI"], urls=["https://example.com"]
        )
        meta = load_metadata(urn)
        assert meta["summary"] == "A summary"
        assert meta["topics"] == ["AI"]
        assert meta["urls"] == ["https://example.com"]

    def test_update_preserves_urls(self):
        urn = "urn:li:ugcPost:789"
        save_content(urn, "Post content")
        save_metadata(
            urn, urls=["https://x.com"], post_url="https://linkedin.com/feed/..."
        )
        update_summary_metadata(urn, "Summary", ["topic1"], ["py"], ["Alice"], "paper")
        meta = load_metadata(urn)
        assert meta["summary"] == "Summary"
        assert meta["urls"] == ["https://x.com"]
        assert meta["post_url"] == "https://linkedin.com/feed/..."
        assert "summarized_at" in meta


class TestNeedsSummary:
    def test_no_content(self):
        assert needs_summary("urn:li:ugcPost:no_content") is False

    def test_content_without_summary(self):
        urn = "urn:li:ugcPost:needs_summary"
        save_content(urn, "x" * 100)
        assert needs_summary(urn) is True

    def test_content_with_summary(self):
        urn = "urn:li:ugcPost:has_summary"
        save_content(urn, "x" * 100)
        save_metadata(urn, summary="Done")
        assert needs_summary(urn) is False


class TestListPostsNeedingSummary:
    def test_filters_by_summary(self):
        save_content("urn:li:ugcPost:a", "a" * 100)
        save_content("urn:li:ugcPost:b", "b" * 100)
        save_metadata("urn:li:ugcPost:b", summary="Done")
        posts = list_posts_needing_summary()
        assert len(posts) == 1
        assert posts[0]["urn"] == "urn:li:ugcPost:a"
        assert posts[0]["content"] == "a" * 100


class TestUpdateUrlsMetadata:
    def test_sets_urls_on_new_urn(self):
        urn = "urn:li:ugcPost:urls_new"
        update_urls_metadata(urn, ["https://example.com"])
        meta = load_metadata(urn)
        assert meta is not None
        assert meta["urls"] == ["https://example.com"]

    def test_preserves_existing_summary(self):
        urn = "urn:li:ugcPost:urls_preserve"
        save_content(urn, "Post text")
        save_metadata(urn, summary="Keep me", topics=["AI"])
        update_urls_metadata(urn, ["https://arxiv.org/abs/123"])
        meta = load_metadata(urn)
        assert meta["summary"] == "Keep me"
        assert meta["topics"] == ["AI"]
        assert meta["urls"] == ["https://arxiv.org/abs/123"]

    def test_overwrites_existing_urls(self):
        urn = "urn:li:ugcPost:urls_overwrite"
        save_metadata(urn, urls=["https://old.example.com"])
        update_urls_metadata(urn, ["https://new.example.com"])
        meta = load_metadata(urn)
        assert meta["urls"] == ["https://new.example.com"]

    def test_empty_list(self):
        urn = "urn:li:ugcPost:urls_empty"
        update_urls_metadata(urn, [])
        meta = load_metadata(urn)
        assert meta["urls"] == []


class TestDeduplication:
    def test_same_urn_one_file(self):
        """Multiple saves for same URN → one content file."""
        post_urn = "urn:li:ugcPost:xyz"
        content = "This is the post body."
        save_content(post_urn, content)
        save_content(post_urn, content)
        assert load_content(post_urn) == content
        content_dir = content_path(post_urn).parent
        assert len(list(content_dir.glob("*.md"))) == 1
