"""Tests for report cache and prompt debug in gradio_app."""

import json
import pytest

from linkedin_api.gradio_app import (
    CONTENT_LEVEL_MINIMAL,
    CONTENT_LEVEL_SUMMARY,
    REPORT_MODE_SINGLE_PASS,
    _REPORT_CACHE_FILE,
    _REPORT_CACHE_VERSION,
    _REPORT_PROMPT_DEBUG_FILE,
    _format_post_for_prompt,
    _load_report_cache,
    _load_report_prompt_debug,
    _save_report_cache,
    _save_report_prompt_debug,
)


@pytest.fixture(autouse=True)
def use_tmp_data_dir(monkeypatch, tmp_path):
    """Use a temp directory for cache/prompt files, not user-level data dir."""
    monkeypatch.setenv("LINKEDIN_DATA_DIR", str(tmp_path))


class TestReportCache:
    def test_cache_hit_when_params_match(self):
        sig = (
            "anthropic:claude-3-haiku",
            10,
            ("ts1", "ts2"),
            REPORT_MODE_SINGLE_PASS,
            CONTENT_LEVEL_SUMMARY,
            50,
            1500,
            "7d",
        )
        report = "## Test Report\n\n- Item 1"
        _save_report_cache(report, sig)
        result = _load_report_cache(
            report_mode=REPORT_MODE_SINGLE_PASS,
            content_level=CONTENT_LEVEL_SUMMARY,
            max_posts=50,
            max_full_post_chars=1500,
            period="7d",
        )
        assert result is not None
        assert result[0] == report
        assert result[1] == sig

    def test_cache_miss_when_content_level_differs(self):
        sig = (
            "anthropic:claude-3-haiku",
            10,
            ("ts1",),
            REPORT_MODE_SINGLE_PASS,
            CONTENT_LEVEL_MINIMAL,
            100,
            1500,
            "7d",
        )
        _save_report_cache("Cached report", sig)
        result = _load_report_cache(
            report_mode=REPORT_MODE_SINGLE_PASS,
            content_level=CONTENT_LEVEL_SUMMARY,
            max_posts=100,
            max_full_post_chars=1500,
            period="7d",
        )
        assert result is None

    def test_cache_uses_tmp_path_not_user_home(self, tmp_path):
        _save_report_cache("test", ("x", 1, (), "per", "minimal", 50, 1500, "7d"))
        cache_file = tmp_path / _REPORT_CACHE_FILE
        assert cache_file.exists()
        data = json.loads(cache_file.read_text())
        assert data["report"] == "test"
        assert data["report_cache_version"] == _REPORT_CACHE_VERSION


class TestReportPromptDebug:
    def test_save_and_load_prompt(self):
        _save_report_prompt_debug(
            "single-pass",
            "System instruction",
            ["User prompt with Summary: my post summary here"],
        )
        content = _load_report_prompt_debug()
        assert "Summary: my post summary here" in content
        assert "User prompt" in content

    def test_prompt_includes_summary_when_summary_level(self):
        meta = {
            "post_url": "https://linkedin.com/feed/update/123",
            "category": "tutorial",
            "topics": ["AI"],
            "summary": "This post explains how to use transformers.",
        }
        formatted = _format_post_for_prompt(meta, CONTENT_LEVEL_SUMMARY)
        assert "Summary: This post explains how to use transformers." in formatted

    def test_prompt_excludes_summary_when_minimal_level(self):
        meta = {
            "post_url": "https://linkedin.com/feed/update/123",
            "category": "tutorial",
            "topics": ["AI"],
            "summary": "This post explains how to use transformers.",
        }
        formatted = _format_post_for_prompt(meta, CONTENT_LEVEL_MINIMAL)
        assert "Summary:" not in formatted
        assert "transformers" not in formatted

    def test_prompt_includes_reaction_and_post_time_when_present(self):
        meta = {
            "post_url": "https://linkedin.com/feed/update/123",
            "category": "tutorial",
            "summary": "A summary.",
            "reaction_time": "2025-03-01T12:00:00+0000",
            "post_time": "2025-02-15T10:00:00+0000",
        }
        formatted = _format_post_for_prompt(meta, CONTENT_LEVEL_SUMMARY)
        assert "Activity: 2025-03-01T12:00:00+0000" in formatted
        assert "Posted: 2025-02-15T10:00:00+0000" in formatted

    def test_prompt_file_in_tmp_path_not_user_home(self, tmp_path):
        _save_report_prompt_debug("test", "sys", ["prompt"])
        prompt_file = tmp_path / _REPORT_PROMPT_DEBUG_FILE
        assert prompt_file.exists()
        assert "prompt" in prompt_file.read_text()
