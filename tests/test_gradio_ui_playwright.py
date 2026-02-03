"""
E2E test: launch Gradio review UI and check key elements with Playwright.

Run (unit tests only, no browser): uv run pytest tests/ -v -m "not integration"
Run this UI test: uv run pytest tests/test_gradio_ui_playwright.py -v -m integration
  - First time: uv run playwright install chromium
  - Test starts the review-only app on port 7862, opens Chromium, asserts page content, then exits.
  - Skips if Chromium is not installed.
"""

import os
import socket
import subprocess
import sys
import time

import pytest

# Port for test server (avoid 7860 in case user runs app)
TEST_PORT = 7862


def _server_ready(port: int, timeout: float = 30.0) -> bool:
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except OSError:
            time.sleep(0.2)
    return False


@pytest.mark.integration
def test_gradio_review_ui_loads():
    """Start review-only Gradio app in subprocess; use Playwright to check page content."""
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    launch_script = """
import os
os.environ.setdefault("PORT", "7862")
from linkedin_api.gradio_review import create_review_interface
demo = create_review_interface()
demo.launch(server_name="127.0.0.1", server_port=7862, share=False)
"""
    proc = subprocess.Popen(
        [sys.executable, "-c", launch_script],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        env={**os.environ, "PORT": str(TEST_PORT)},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        if not _server_ready(TEST_PORT):
            stderr = proc.stderr.read().decode() if proc.stderr else ""
            proc.terminate()
            proc.wait(timeout=5)
            pytest.fail(f"Server did not become ready on port {TEST_PORT}. stderr: {stderr[:500]}")
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                try:
                    page = browser.new_page()
                    page.goto(f"http://127.0.0.1:{TEST_PORT}", wait_until="domcontentloaded", timeout=15000)
                    # Gradio keeps connections open; don't wait for networkidle
                    page.wait_for_selector("button", timeout=10000)
                    # Should show review UI
                    content = page.content()
                    assert "LinkedIn Extraction Review" in content or "Extraction Review" in content
                    assert "Load from API" in content or "Load" in content
                    assert "Enrichment preview" in content or "Extract author" in content
                finally:
                    browser.close()
        except Exception as e:
            err_str = str(e)
            if "Executable doesn't exist" in err_str or "playwright install" in err_str.lower():
                pytest.skip(
                    "Playwright browsers not installed. Run: uv run playwright install chromium"
                )
            raise
    finally:
        proc.terminate()
        proc.wait(timeout=10)
