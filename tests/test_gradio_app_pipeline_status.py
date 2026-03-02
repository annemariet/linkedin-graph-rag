"""Unit tests for pipeline progress rendering in gradio_app."""

import pytest

from linkedin_api.gradio_app import (
    PIPELINE_HINT_TEXT,
    _render_pipeline_status,
    _status_from_pipeline_line,
)


def test_render_pipeline_status_shows_hint_when_idle():
    html = _render_pipeline_status()
    assert PIPELINE_HINT_TEXT in html


def test_render_pipeline_status_shows_label_and_progress_width():
    html = _render_pipeline_status("Enriching…", 0.256)
    assert "Enriching…" in html
    assert "width: 26%;" in html


def test_render_pipeline_status_escapes_label_html():
    html = _render_pipeline_status('<script>alert("x")</script>', 0.5)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_status_from_pipeline_line_parses_enriching_fraction():
    progress, label = _status_from_pipeline_line("Enriching 3/10…")
    assert progress == pytest.approx(0.26)
    assert label == "Enriching…"


def test_status_from_pipeline_line_parses_summarizing_fraction():
    progress, label = _status_from_pipeline_line("Summarizing batch 2/4…")
    assert progress == 0.5
    assert label == "Summarizing…"


def test_status_from_pipeline_line_handles_failures():
    assert _status_from_pipeline_line("❌ Failed: boom") == (1.0, "Failed.")
