"""
Test enrichment preview formatting and author extraction with details.

Run: uv run pytest tests/test_gradio_review_enrichment.py -v
"""

import json
from unittest.mock import patch

import pytest

from linkedin_api.gradio_review import (
    _format_author_result,
    _format_resources_result,
)
from linkedin_api.enrich_profiles import extract_author_profile_with_details


class TestFormatAuthorResult:
    """_format_author_result shows URL tried, status, and result."""

    def test_no_url(self):
        out = _format_author_result({"url_tried": "", "error": "No URL provided."})
        assert "URL tried:" in out
        assert "No URL provided" in out

    def test_404(self):
        out = _format_author_result({
            "url_tried": "https://example.com/post",
            "normalized_url": "https://example.com/post",
            "status_code": 404,
            "error": "Not found (404).",
        })
        assert "URL tried:" in out
        assert "404" in out
        assert "Not found" in out or "404" in out

    def test_success(self):
        out = _format_author_result({
            "url_tried": "https://linkedin.com/feed/update/urn:li:share:1",
            "normalized_url": "https://linkedin.com/feed/update/urn:li:share:1",
            "status_code": 200,
            "author": {"name": "Jane Doe", "profile_url": "https://www.linkedin.com/in/janedoe"},
        })
        assert "URL tried:" in out
        assert "Jane Doe" in out
        assert "profile_url" in out

    def test_skip_reason(self):
        out = _format_author_result({
            "url_tried": "https://linkedin.com/feed/update/urn:li:groupPost:123",
            "normalized_url": "https://linkedin.com/feed/update/urn:li:groupPost:123",
            "skip_reason": "Private or group post URL; not fetched.",
        })
        assert "Private" in out or "not fetched" in out


class TestFormatResourcesResult:
    """_format_resources_result shows content snippet and URLs found."""

    def test_with_content_and_urls(self):
        content = "Check out https://github.com/foo and https://example.com"
        urls = ["https://github.com/foo", "https://example.com"]
        out = _format_resources_result(content, urls, "extracted")
        assert "Content used (extracted):" in out
        assert "https://github.com/foo" in content or "https://github.com/foo" in out
        assert "URLs found:" in out
        assert "https://github.com/foo" in out
        assert "https://example.com" in out

    def test_no_content(self):
        out = _format_resources_result("", [], "raw API")
        assert "No post/comment text" in out
        assert "URLs found: None" in out

    def test_content_no_urls(self):
        out = _format_resources_result("Just some text with no links.", [], "extracted")
        assert "Just some text" in out
        assert "URLs found: None" in out


class TestExtractAuthorProfileWithDetails:
    """extract_author_profile_with_details returns structured details."""

    def test_empty_url(self):
        details = extract_author_profile_with_details("")
        assert details["error"] == "No URL provided."
        assert details["url_tried"] == ""

    def test_404_returns_status_and_error(self):
        with patch("linkedin_api.enrich_profiles.requests.get") as m:
            m.return_value.status_code = 404
            details = extract_author_profile_with_details(
                "https://www.linkedin.com/feed/update/urn:li:share:999999999999"
            )
        assert details["status_code"] == 404
        assert "404" in (details.get("error") or "")
