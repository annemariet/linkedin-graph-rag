"""
Test thumbnail generation with Playwright.

Run: uv run pytest tests/test_enrich_thumbnails.py -v
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from linkedin_api.enrich_profiles import _ensure_thumbnail, get_thumbnail_path_for_url


@pytest.mark.unit
class TestEnsureThumbnail:
    """_ensure_thumbnail generates screenshots from HTML files."""

    def test_simple_html_generates_thumbnail(self):
        """Simple HTML should generate a thumbnail successfully."""
        html_content = """<!DOCTYPE html>
<html>
<head><title>Test</title></head>
<body><h1>Test Page</h1><p>Content</p></body>
</html>"""
        with tempfile.TemporaryDirectory() as tmpdir:
            html_path = Path(tmpdir) / "test.html"
            png_path = Path(tmpdir) / "test.png"
            html_path.write_text(html_content)

            result = _ensure_thumbnail(html_path, png_path)

            assert result == png_path
            assert png_path.exists()
            assert png_path.stat().st_size > 0

    def test_existing_thumbnail_is_reused(self):
        """If PNG already exists, return it without regenerating."""
        html_content = "<html><body>Test</body></html>"
        with tempfile.TemporaryDirectory() as tmpdir:
            html_path = Path(tmpdir) / "test.html"
            png_path = Path(tmpdir) / "test.png"
            html_path.write_text(html_content)
            png_path.write_bytes(b"fake png content")

            result = _ensure_thumbnail(html_path, png_path)

            assert result == png_path
            assert png_path.read_bytes() == b"fake png content"

    def test_missing_html_returns_none(self):
        """Missing HTML file should return None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            html_path = Path(tmpdir) / "nonexistent.html"
            png_path = Path(tmpdir) / "test.png"

            result = _ensure_thumbnail(html_path, png_path)

            assert result is None
            assert not png_path.exists()

    def test_external_requests_blocked(self):
        """External network requests should be blocked to prevent timeouts."""
        # HTML with external resources that would normally cause timeouts
        html_content = """<!DOCTYPE html>
<html>
<head>
    <link rel="stylesheet" href="https://example.com/style.css">
    <script src="https://example.com/script.js"></script>
</head>
<body>
    <img src="https://example.com/image.jpg" alt="External image">
    <h1>Test Page</h1>
</body>
</html>"""
        with tempfile.TemporaryDirectory() as tmpdir:
            html_path = Path(tmpdir) / "test.html"
            png_path = Path(tmpdir) / "test.png"
            html_path.write_text(html_content)

            # Should succeed despite external resources (they're blocked)
            result = _ensure_thumbnail(html_path, png_path)

            assert result == png_path
            assert png_path.exists()

    def test_playwright_not_installed_returns_none(self):
        """If Playwright is not installed, return None gracefully."""
        html_content = "<html><body>Test</body></html>"
        with tempfile.TemporaryDirectory() as tmpdir:
            html_path = Path(tmpdir) / "test.html"
            png_path = Path(tmpdir) / "test.png"
            html_path.write_text(html_content)

            # Patch the import statement inside the function
            original_import = __import__

            def mock_import(name, *args, **kwargs):
                if name == "playwright.sync_api":
                    raise ImportError("No module named 'playwright'")
                return original_import(name, *args, **kwargs)

            with patch("builtins.__import__", side_effect=mock_import):
                # Reload module to trigger import error in the try/except
                import linkedin_api.enrich_profiles
                import importlib

                importlib.reload(linkedin_api.enrich_profiles)
                # Re-import after reload
                from linkedin_api.enrich_profiles import _ensure_thumbnail

                result = _ensure_thumbnail(html_path, png_path)

            assert result is None
            assert not png_path.exists()


@pytest.mark.unit
class TestGetThumbnailPathForUrl:
    """get_thumbnail_path_for_url returns thumbnail path or None."""

    def test_disabled_thumbnails_env_returns_none(self):
        """DISABLE_THUMBNAILS=1 should skip thumbnail generation."""
        with patch.dict("os.environ", {"DISABLE_THUMBNAILS": "1"}):
            result = get_thumbnail_path_for_url("https://linkedin.com/feed/update/123")
            assert result is None

    def test_no_cache_dir_returns_none(self):
        """If cache directory cannot be created, return None."""
        with patch(
            "linkedin_api.enrich_profiles._post_html_cache_dir", return_value=None
        ):
            result = get_thumbnail_path_for_url("https://linkedin.com/feed/update/123")
            assert result is None
