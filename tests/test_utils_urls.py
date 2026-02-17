"""Tests for linkedin_api.utils.urls module."""

from linkedin_api.utils.urls import (
    categorize_url,
    extract_urls_from_text,
    should_ignore_url,
)


class TestExtractUrlsFromText:
    def test_basic_url(self):
        urls = extract_urls_from_text("Check out https://example.com/page")
        assert "https://example.com/page" in urls

    def test_multiple_urls(self):
        text = "See https://a.com and https://b.com for details"
        urls = extract_urls_from_text(text)
        assert len(urls) == 2

    def test_empty_text(self):
        assert extract_urls_from_text("") == []
        assert extract_urls_from_text(None) == []

    def test_no_urls(self):
        assert extract_urls_from_text("No URLs here") == []

    def test_dedup(self):
        text = "https://a.com and https://a.com again"
        urls = extract_urls_from_text(text)
        assert len(urls) == 1


class TestCategorizeUrl:
    def test_github(self):
        result = categorize_url("https://github.com/user/repo")
        assert result["type"] == "repository"

    def test_youtube(self):
        result = categorize_url("https://youtube.com/watch?v=123")
        assert result["type"] == "video"

    def test_medium(self):
        result = categorize_url("https://medium.com/@user/article")
        assert result["type"] == "article"

    def test_pdf(self):
        result = categorize_url("https://example.com/doc.pdf")
        assert result["type"] == "document"


class TestShouldIgnoreUrl:
    def test_linkedin_profile(self):
        assert should_ignore_url("https://linkedin.com/in/john") is True

    def test_linkedin_hashtag(self):
        assert should_ignore_url("https://linkedin.com/feed/hashtag/ai") is True

    def test_external_url(self):
        assert should_ignore_url("https://github.com/repo") is False
