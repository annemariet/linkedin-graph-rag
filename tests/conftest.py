"""
Pytest configuration and hooks.

Ensures Playwright Chromium is available when running thumbnail tests in a fresh env.
"""

import subprocess
import sys


def _chromium_launch_ok():
    """Return True if Playwright Chromium can be launched."""
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        return True
    except Exception:
        return False


def pytest_collection_finish(session):
    """After collection: install Playwright Chromium if thumbnail tests are run and it's missing."""
    if not session.items:
        return
    has_thumb_tests = any(
        "test_enrich_thumbnails" in str(getattr(item, "fspath", ""))
        for item in session.items
    )
    if not has_thumb_tests:
        return
    if _chromium_launch_ok():
        return
    # Install Chromium so thumbnail tests can run (CI does this explicitly; local may need it once)
    subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        capture_output=True,
        timeout=120,
        check=False,
    )
