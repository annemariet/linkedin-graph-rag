"""Tests for linkedin_api.utils.urls module."""

import pytest
from unittest.mock import MagicMock, patch

from linkedin_api.utils.urls import (
    categorize_url,
    extract_urls_from_text,
    resolve_redirect,
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


class TestResolveRedirect:
    """Tests for lnkd.in interstitial page parsing."""

    def _mock_lnkd_response(self, page_text: str, final_url: str = "") -> MagicMock:
        """Build a mock requests.get response for a lnkd.in page."""
        resp = MagicMock()
        resp.url = (
            final_url or "https://lnkd.in/erbBvi7E"
        )  # unchanged = no HTTP redirect
        resp.text = page_text
        return resp

    @patch("requests.get")
    def test_lnkd_in_url_in_interstitial_text(self, mock_get):
        """LinkedIn interstitial page includes the target URL in plain text."""
        page = (
            "<html><body>"
            "<p>This link will take you to a page that's not on LinkedIn</p>"
            "<p>Because this is an external link, we're unable to verify it for safety.</p>"
            "<p>https://presse.economie.gouv.fr/acces-illegitimes-au-fichier-national-des-comptes-bancaires-ficoba/</p>"
            "</body></html>"
        )
        mock_get.return_value = self._mock_lnkd_response(page)

        result = resolve_redirect("https://lnkd.in/erbBvi7E")

        assert (
            result
            == "https://presse.economie.gouv.fr/acces-illegitimes-au-fichier-national-des-comptes-bancaires-ficoba/"
        )

    @patch("requests.get")
    def test_lnkd_in_filters_linkedin_and_static_assets(self, mock_get):
        """LinkedIn static assets and internal URLs are skipped; the external URL is returned."""
        page = (
            "<html><head>"
            '<link rel="stylesheet" href="https://static.licdn.com/aero-v1/sc/h/abc.css"/>'
            '<link rel="icon" href="https://static.licdn.com/sc/h/favicon.ico"/>'
            "</head><body>"
            "<p>Continue to https://github.com/user/interesting-repo</p>"
            "</body></html>"
        )
        mock_get.return_value = self._mock_lnkd_response(page)

        result = resolve_redirect("https://lnkd.in/eXYZabc")

        assert result == "https://github.com/user/interesting-repo"
        assert "static.licdn.com" not in result

    @patch("requests.get")
    def test_lnkd_in_http_redirect_takes_priority(self, mock_get):
        """If requests follows an HTTP redirect away from lnkd.in, use that immediately."""
        resp = MagicMock()
        resp.url = "https://example.com/final"  # HTTP redirect worked
        resp.text = "<html><body>some page</body></html>"
        mock_get.return_value = resp

        result = resolve_redirect("https://lnkd.in/eXYZabc")

        assert result == "https://example.com/final"

    @patch("requests.get")
    def test_lnkd_in_meta_refresh_takes_priority_over_body(self, mock_get):
        """<meta refresh> takes priority over body text extraction."""
        page = (
            '<html><head><meta http-equiv="refresh" content="0;url=https://meta-target.com/page"/></head>'
            "<body><p>Also see https://body-target.com/other</p></body></html>"
        )
        mock_get.return_value = self._mock_lnkd_response(page)

        result = resolve_redirect("https://lnkd.in/eXYZabc")

        assert result == "https://meta-target.com/page"

    @patch("requests.get")
    def test_lnkd_in_anchor_link_fallback(self, mock_get):
        """If no URL in page text, falls back to first external anchor href."""
        page = (
            "<html><body>"
            '<a href="https://www.linkedin.com/safety/go?url=...">skip</a>'
            '<a href="https://actual-target.org/article">Continue</a>'
            "</body></html>"
        )
        mock_get.return_value = self._mock_lnkd_response(page)

        result = resolve_redirect("https://lnkd.in/eXYZabc")

        assert result == "https://actual-target.org/article"

    @patch("requests.get")
    def test_lnkd_in_returns_original_when_no_url_found(self, mock_get):
        """Falls back to original URL if nothing useful is found in the page."""
        page = "<html><body><p>Nothing to see here.</p></body></html>"
        mock_get.return_value = self._mock_lnkd_response(page)

        original = "https://lnkd.in/erbBvi7E"
        result = resolve_redirect(original)

        assert result == original

    def test_non_lnkd_in_uses_head_redirect(self):
        """Non lnkd.in URLs use HEAD-based redirect resolution, not HTML parsing."""
        with patch("requests.get") as mock_get, patch("requests.head") as mock_head:
            mock_head.return_value = MagicMock(url="https://final.example.com/page")
            result = resolve_redirect("https://short.example.com/abc")

        mock_get.assert_not_called()
        assert result == "https://final.example.com/page"

    @pytest.mark.integration
    def test_real_lnkd_in_erbBvi7E(self):
        """Live: https://lnkd.in/erbBvi7E should resolve to the French government press release."""
        result = resolve_redirect("https://lnkd.in/erbBvi7E")
        assert "presse.economie.gouv.fr" in result


class TestShouldIgnoreUrl:
    def test_linkedin_profile(self):
        assert should_ignore_url("https://linkedin.com/in/john") is True

    def test_linkedin_hashtag(self):
        assert should_ignore_url("https://linkedin.com/feed/hashtag/ai") is True

    def test_external_url(self):
        assert should_ignore_url("https://github.com/repo") is False
