"""Unit tests for extract_resources module."""

from unittest.mock import MagicMock, patch
import pytest

from linkedin_api.extract_resources import (
    extract_urls_from_text,
    categorize_url,
    should_ignore_url,
    resolve_redirect,
    extract_title_from_url,
)


class TestExtractUrlsFromText:
    """Test URL extraction from text."""

    def test_extract_simple_url(self):
        """Test extracting a simple HTTP URL."""
        text = "Check out https://example.com for more info"
        urls = extract_urls_from_text(text)
        assert "https://example.com" in urls

    def test_extract_multiple_urls(self):
        """Test extracting multiple URLs."""
        text = "Visit https://example.com and https://test.org"
        urls = extract_urls_from_text(text)
        assert len(urls) == 2
        assert "https://example.com" in urls
        assert "https://test.org" in urls

    def test_extract_url_with_trailing_punctuation(self):
        """Test that trailing punctuation is removed."""
        text = "See https://example.com."
        urls = extract_urls_from_text(text)
        assert "https://example.com" in urls
        assert "https://example.com." not in urls

    def test_empty_text(self):
        """Test that empty text returns empty list."""
        assert extract_urls_from_text("") == []
        assert extract_urls_from_text(None) == []

    def test_no_urls(self):
        """Test that text without URLs returns empty list."""
        assert extract_urls_from_text("Just some text") == []


class TestCategorizeUrl:
    """Test URL categorization."""

    def test_categorize_youtube(self):
        """Test categorizing YouTube URLs."""
        result = categorize_url("https://www.youtube.com/watch?v=123")
        assert result["type"] == "video"
        assert "youtube.com" in result["domain"]

    def test_categorize_github(self):
        """Test categorizing GitHub URLs."""
        result = categorize_url("https://github.com/user/repo")
        assert result["type"] == "repository"
        assert "github.com" in result["domain"]

    def test_categorize_article(self):
        """Test categorizing article URLs."""
        result = categorize_url("https://example.com/article")
        assert result["type"] == "article"

    def test_categorize_linkedin_article(self):
        """Test categorizing LinkedIn article URLs."""
        result = categorize_url("https://www.linkedin.com/pulse/article-title")
        assert result["type"] == "article"

    def test_remove_www_prefix(self):
        """Test that www. prefix is removed from domain."""
        result = categorize_url("https://www.example.com")
        assert result["domain"] == "example.com"


class TestShouldIgnoreUrl:
    """Test URL filtering logic."""

    def test_ignore_linkedin_profile(self):
        """Test that LinkedIn profile URLs are ignored."""
        assert should_ignore_url("https://www.linkedin.com/in/username") is True

    def test_ignore_linkedin_hashtag(self):
        """Test that LinkedIn hashtag URLs are ignored."""
        assert should_ignore_url("https://www.linkedin.com/feed/hashtag/python") is True

    def test_ignore_linkedin_company(self):
        """Test that LinkedIn company URLs are ignored."""
        assert should_ignore_url("https://www.linkedin.com/company/example") is True

    def test_allow_external_url(self):
        """Test that external URLs are not ignored."""
        assert should_ignore_url("https://example.com/article") is False

    def test_allow_linkedin_article(self):
        """Test that LinkedIn article URLs are not ignored."""
        assert should_ignore_url("https://www.linkedin.com/pulse/article") is False


class TestResolveRedirect:
    """Test redirect resolution."""

    @patch("linkedin_api.extract_resources.requests.head")
    def test_resolve_redirect_success(self, mock_head):
        """Test successful redirect resolution."""
        mock_response = MagicMock()
        mock_response.url = "https://final-url.com"
        mock_head.return_value = mock_response

        result = resolve_redirect("https://short.ly/abc")
        assert result == "https://final-url.com"

    @patch("linkedin_api.extract_resources.requests.head")
    @patch("linkedin_api.extract_resources.requests.get")
    def test_resolve_redirect_fallback_to_get(self, mock_get, mock_head):
        """Test fallback to GET when HEAD fails."""
        mock_head.side_effect = Exception("HEAD failed")
        mock_response = MagicMock()
        mock_response.url = "https://final-url.com"
        mock_get.return_value = mock_response

        result = resolve_redirect("https://short.ly/abc")
        assert result == "https://final-url.com"

    @patch("linkedin_api.extract_resources.requests.head")
    @patch("linkedin_api.extract_resources.requests.get")
    def test_resolve_redirect_returns_original_on_failure(self, mock_get, mock_head):
        """Test that original URL is returned on failure."""
        mock_head.side_effect = Exception("HEAD failed")
        mock_get.side_effect = Exception("GET failed")

        original_url = "https://short.ly/abc"
        result = resolve_redirect(original_url)
        assert result == original_url

    def test_resolve_no_redirect(self):
        """Test that non-redirecting URLs return unchanged."""
        with patch("linkedin_api.extract_resources.requests.head") as mock_head:
            mock_response = MagicMock()
            mock_response.url = "https://example.com"
            mock_head.return_value = mock_response

            result = resolve_redirect("https://example.com")
            assert result == "https://example.com"


class TestExtractTitleFromUrl:
    """Test title extraction from URLs."""

    @patch("linkedin_api.extract_resources.requests.get")
    def test_extract_title_from_html(self, mock_get):
        """Test extracting title from HTML page."""
        mock_response = MagicMock()
        mock_response.text = "<html><head><title>Test Title</title></head></html>"
        mock_response.headers = {"content-type": "text/html"}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        title = extract_title_from_url("https://example.com")
        assert title == "Test Title"

    @patch("linkedin_api.extract_resources.requests.get")
    def test_extract_title_from_og_tag(self, mock_get):
        """Test extracting title from Open Graph tag."""
        mock_response = MagicMock()
        mock_response.text = (
            '<html><head><meta property="og:title" content="OG Title" /></head></html>'
        )
        mock_response.headers = {"content-type": "text/html"}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        title = extract_title_from_url("https://example.com")
        assert title == "OG Title"

    @patch("linkedin_api.extract_resources.requests.get")
    def test_extract_title_from_twitter_card(self, mock_get):
        """Test extracting title from Twitter Card tag."""
        mock_response = MagicMock()
        mock_response.text = '<html><head><meta name="twitter:title" content="Twitter Title" /></head></html>'
        mock_response.headers = {"content-type": "text/html"}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        title = extract_title_from_url("https://example.com")
        assert title == "Twitter Title"

    @patch("linkedin_api.extract_resources.requests.get")
    def test_extract_title_non_html_content(self, mock_get):
        """Test that non-HTML content returns None."""
        mock_response = MagicMock()
        mock_response.headers = {"content-type": "application/json"}
        mock_get.return_value = mock_response

        title = extract_title_from_url("https://example.com/api")
        assert title is None

    @patch("linkedin_api.extract_resources.requests.get")
    def test_extract_title_request_failure(self, mock_get):
        """Test that request failures return None."""
        mock_get.side_effect = Exception("Request failed")

        title = extract_title_from_url("https://example.com")
        assert title is None


class TestLnkdInRedirect:
    """Test lnkd.in redirect handling (example from ticket LUC-11)."""

    @patch("linkedin_api.extract_resources.requests.head")
    def test_resolve_lnkd_in_redirect(self, mock_head):
        """Test that lnkd.in URLs are resolved to final URLs."""
        mock_response = MagicMock()
        mock_response.url = "https://dicioccio.fr/postgrest-over-cloudrun.html"
        mock_head.return_value = mock_response

        result = resolve_redirect("https://lnkd.in/ep4kistt")
        assert result == "https://dicioccio.fr/postgrest-over-cloudrun.html"

    def test_extract_url_from_linkedin_post_content(self):
        """Test extracting external URLs from LinkedIn post content."""
        # Example: post content containing lnkd.in URL
        post_content = "Check out this article: https://lnkd.in/ep4kistt"
        urls = extract_urls_from_text(post_content)
        assert "https://lnkd.in/ep4kistt" in urls

    def test_ignore_linkedin_feed_update_urls(self):
        """Test that LinkedIn feed update URLs are ignored (they're internal LinkedIn URLs, not external resources)."""
        # LinkedIn feed update URLs should be ignored - they're internal LinkedIn URLs
        # We want to extract external resources FROM the content of those posts,
        # but not create Resource nodes for the post URLs themselves
        assert (
            should_ignore_url(
                "https://www.linkedin.com/feed/update/urn:li:activity:7405903017427800064/"
            )
            is True
        )
        assert should_ignore_url("https://www.linkedin.com/feed/") is True
