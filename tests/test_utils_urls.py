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

    def _mock_lnkd_response(
        self, page_text: str, final_url: str = "", status_code: int = 200
    ) -> MagicMock:
        """Build a mock requests.get response for a lnkd.in page."""
        resp = MagicMock()
        resp.status_code = status_code
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
    def test_lnkd_in_ignores_urls_in_html_attributes(self, mock_get):
        """URLs in HTML attributes (stylesheet href, favicon) are not visible
        to get_text() and are therefore never returned."""
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

    @patch("requests.get")
    def test_lnkd_in_returns_original_when_no_url_found(self, mock_get):
        """Falls back to original URL if nothing useful is found in the page."""
        page = "<html><body><p>Nothing to see here.</p></body></html>"
        mock_get.return_value = self._mock_lnkd_response(page)

        original = "https://lnkd.in/erbBvi7E"
        result = resolve_redirect(original)

        assert result == original

    @patch("requests.get")
    def test_lnkd_in_direct_redirect_uses_final_url_on_406(self, mock_get):
        """When lnkd.in redirects directly (no interstitial), final server may return 406.
        We use response.url to get the resolved target."""
        mock_get.return_value = self._mock_lnkd_response(
            "", final_url="https://github.com/datagouv/datagouv-mcp", status_code=406
        )

        result = resolve_redirect("https://lnkd.in/eAWEsmVw")

        assert result == "https://github.com/datagouv/datagouv-mcp"

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

    @pytest.mark.integration
    def test_real_lnkd_in_eAWEsmVw_resolves_to_github_datagouv_mcp(self):
        """Live: lnkd.in/eAWEsmVw gives HTTP 406 (no interstitial) but redirects to GitHub.
        We should resolve to github.com/datagouv/datagouv-mcp."""
        result = resolve_redirect("https://lnkd.in/eAWEsmVw")
        assert "github.com" in result
        assert "datagouv" in result

    @pytest.mark.integration
    def test_real_lnkd_in_eMcHSAFH_resolves_to_stats_agriculture_with_ssl_verify_off(
        self, monkeypatch
    ):
        """Live: lnkd.in/eMcHSAFH redirects to stats.agriculture.gouv.fr which has SSL cert
        issues. With REQUESTS_SSL_VERIFY=false, we should resolve to the target."""
        import warnings

        import urllib3

        monkeypatch.setenv("REQUESTS_SSL_VERIFY", "false")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", urllib3.exceptions.InsecureRequestWarning)
            result = resolve_redirect("https://lnkd.in/eMcHSAFH")
        assert "stats.agriculture.gouv.fr" in result
        assert "cartostat" in result

    @pytest.mark.integration
    def test_real_lnkd_in_geemzfeQ_resolves_to_theshamblog(self):
        """Live: lnkd.in/geemzfeQ should show LinkedIn interstitial with target
        https://theshamblog.com/an-ai-agent-wrote-a-hit-piece-on-me-part-4/"""
        result = resolve_redirect("https://lnkd.in/geemzfeQ")
        assert "theshamblog.com" in result


class TestShouldIgnoreUrl:
    def test_linkedin_profile(self):
        assert should_ignore_url("https://linkedin.com/in/john") is True

    def test_linkedin_hashtag(self):
        assert should_ignore_url("https://linkedin.com/feed/hashtag/ai") is True

    def test_external_url(self):
        assert should_ignore_url("https://github.com/repo") is False
