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

    def test_categorize_pdf_document(self):
        """Test categorizing PDF documents."""
        result = categorize_url("https://example.com/document.pdf")
        assert result["type"] == "document"

    def test_categorize_video_file(self):
        """Test categorizing video files."""
        result = categorize_url("https://example.com/video.mp4")
        assert result["type"] == "video"

    def test_categorize_image_file(self):
        """Test categorizing image files."""
        result = categorize_url("https://example.com/image.png")
        assert result["type"] == "image"

    def test_categorize_medium_article(self):
        """Test categorizing Medium articles."""
        result = categorize_url("https://medium.com/@user/article-title")
        assert result["type"] == "article"

    def test_categorize_stackoverflow_tool(self):
        """Test categorizing Stack Overflow as tool."""
        result = categorize_url("https://stackoverflow.com/questions/123")
        assert result["type"] == "tool"

    def test_categorize_arxiv_research(self):
        """Test categorizing arXiv as research."""
        result = categorize_url("https://arxiv.org/abs/1234.5678")
        assert result["type"] == "research"

    def test_categorize_blog_path(self):
        """Test categorizing URLs with /blog/ path as article."""
        result = categorize_url("https://example.com/blog/post-title")
        assert result["type"] == "article"

    def test_categorize_gitlab_repository(self):
        """Test categorizing GitLab as repository."""
        result = categorize_url("https://gitlab.com/user/repo")
        assert result["type"] == "repository"


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
        """Test successful redirect resolution with HEAD."""
        mock_response = MagicMock()
        mock_response.url = "https://final-url.com"
        mock_head.return_value = mock_response

        result = resolve_redirect("https://short.ly/abc")
        assert result == "https://final-url.com"
        # Verify headers are passed
        mock_head.assert_called_once()
        call_kwargs = mock_head.call_args[1]
        assert "headers" in call_kwargs
        assert "User-Agent" in call_kwargs["headers"]

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
        # Verify GET was called with headers
        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args[1]
        assert "headers" in call_kwargs
        assert "User-Agent" in call_kwargs["headers"]

    @patch("linkedin_api.extract_resources.requests.head")
    @patch("linkedin_api.extract_resources.requests.get")
    def test_resolve_redirect_head_same_url_fallback_to_get(self, mock_get, mock_head):
        """Test that GET is tried when HEAD returns same URL."""
        # HEAD returns same URL (no redirect detected)
        mock_head_response = MagicMock()
        mock_head_response.url = "https://short.ly/abc"
        mock_head.return_value = mock_head_response

        # GET resolves the redirect
        mock_get_response = MagicMock()
        mock_get_response.url = "https://final-url.com"
        mock_get.return_value = mock_get_response

        result = resolve_redirect("https://short.ly/abc")
        assert result == "https://final-url.com"
        # Both should be called
        assert mock_head.called
        assert mock_get.called

    @patch("linkedin_api.extract_resources.requests.head")
    @patch("linkedin_api.extract_resources.requests.get")
    def test_resolve_redirect_returns_original_on_failure(self, mock_get, mock_head):
        """Test that original URL is returned when both HEAD and GET fail."""
        mock_head.side_effect = Exception("HEAD failed")
        mock_get.side_effect = Exception("GET failed")

        original_url = "https://short.ly/abc"
        result = resolve_redirect(original_url)
        assert result == original_url

    @patch("linkedin_api.extract_resources.requests.head")
    @patch("linkedin_api.extract_resources.requests.get")
    def test_resolve_no_redirect(self, mock_get, mock_head):
        """Test that non-redirecting URLs return unchanged."""
        mock_response = MagicMock()
        mock_response.url = "https://example.com/"
        mock_head.return_value = mock_response
        mock_get.return_value = mock_response

        result = resolve_redirect("https://example.com")
        # requests normalizes URLs, so trailing slash is acceptable
        assert result in ("https://example.com", "https://example.com/")

    @patch("linkedin_api.extract_resources.requests.head")
    def test_resolve_redirect_uses_headers(self, mock_head):
        """Test that redirect resolution includes proper headers."""
        mock_response = MagicMock()
        mock_response.url = "https://final-url.com"
        mock_head.return_value = mock_response

        resolve_redirect("https://short.ly/abc")

        # Verify headers are included
        call_kwargs = mock_head.call_args[1]
        assert "headers" in call_kwargs
        headers = call_kwargs["headers"]
        assert "User-Agent" in headers
        assert "Accept" in headers
        assert "Accept-Language" in headers
        assert "Mozilla" in headers["User-Agent"]


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

    @patch("linkedin_api.extract_resources.requests.get")
    @patch("linkedin_api.extract_resources.requests.head")
    def test_resolve_lnkd_in_redirect_via_get_skips_head(self, mock_head, mock_get):
        """Test that lnkd.in URLs skip HEAD and use GET with HTML parsing."""
        # Mock GET response with HTML containing the final URL (and LinkedIn static assets)
        mock_response = MagicMock()
        mock_response.url = (
            "https://lnkd.in/ep4kistt"  # LinkedIn doesn't redirect via HTTP
        )
        # Simulate LinkedIn page with static assets and the final URL
        mock_response.text = (
            "<html>"
            '<link href="https://static.licdn.com/aero-v1/sc/h/al2o9zrvru7aqj8e1x2rzsrca">'
            "Some content with https://dicioccio.fr/postgrest-over-cloudrun.html in it"
            "</html>"
        )
        mock_get.return_value = mock_response

        result = resolve_redirect("https://lnkd.in/ep4kistt")
        assert result == "https://dicioccio.fr/postgrest-over-cloudrun.html"
        # GET should be called for lnkd.in URLs (we skip HEAD)
        mock_get.assert_called_once()
        # HEAD should NOT be called for lnkd.in URLs
        mock_head.assert_not_called()
        # Verify headers are passed
        call_kwargs = mock_get.call_args[1]
        assert "headers" in call_kwargs
        assert "User-Agent" in call_kwargs["headers"]

    @patch("linkedin_api.extract_resources.requests.get")
    def test_resolve_lnkd_in_filters_static_assets(self, mock_get):
        """Test that lnkd.in URL parsing filters out LinkedIn static assets."""
        mock_response = MagicMock()
        mock_response.url = "https://lnkd.in/ep4kistt"
        # HTML with static assets that should be filtered out
        mock_response.text = (
            "<html>"
            "https://static.licdn.com/aero-v1/sc/h/al2o9zrvru7aqj8e1x2rzsrca.css "
            "https://dicioccio.fr/postgrest-over-cloudrun.html "
            "https://static.licdn.com/scds/common/u/images/logos/favicons/v1/favicon.ico"
            "</html>"
        )
        mock_get.return_value = mock_response

        result = resolve_redirect("https://lnkd.in/ep4kistt")
        # Should extract the final URL, not static assets
        assert result == "https://dicioccio.fr/postgrest-over-cloudrun.html"
        assert "static.licdn.com" not in result
        assert "favicon.ico" not in result

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

    @pytest.mark.integration
    def test_resolve_lnkd_in_redirect_real(self):
        """Integration test: Test that lnkd.in URLs actually resolve to final URLs."""
        # Test with a real lnkd.in URL that redirects to edgeimpulse.com
        short_url = "https://lnkd.in/gGGuuQq9"
        final_url = resolve_redirect(short_url)

        # Should resolve to the final URL, not the short URL
        assert final_url != short_url
        assert "lnkd.in" not in final_url
        # Should resolve to edgeimpulse.com domain
        assert "edgeimpulse.com" in final_url
