"""Unit tests for pipeline progress rendering in gradio_app."""

from linkedin_api.gradio_app import (
    CONTENT_LEVEL_FULL,
    CONTENT_LEVEL_LABEL_FULL,
    CONTENT_LEVEL_LABEL_MINIMAL,
    CONTENT_LEVEL_LABEL_SUMMARY,
    CONTENT_LEVEL_MINIMAL,
    CONTENT_LEVEL_SUMMARY,
    PIPELINE_HINT_TEXT,
    REPORT_MODE_LABEL_SINGLE_PASS,
    REPORT_MODE_PER_CATEGORY,
    REPORT_MODE_SINGLE_PASS,
    _normalize_content_level,
    _normalize_report_mode,
    _render_pipeline_status,
    _status_from_pipeline_line,
)


def test_render_pipeline_status_shows_hint_when_idle():
    html = _render_pipeline_status()
    assert PIPELINE_HINT_TEXT in html


def test_render_pipeline_status_shows_label_and_progress_width():
    html = _render_pipeline_status("enriching [3/10]…", (1, 0.256))
    assert "enriching [3/10]…" in html
    assert "width: 26%;" in html


def test_render_pipeline_status_escapes_label_html():
    html = _render_pipeline_status('<script>alert("x")</script>', (0, 0.5))
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_status_from_pipeline_line_parses_enriching_fraction():
    stage_progress, label = _status_from_pipeline_line("Enriching 3/10…")
    assert stage_progress == (1, 0.3)
    assert label == "enriching [3/10]…"


def test_status_from_pipeline_line_parses_summarizing_fraction():
    stage_progress, label = _status_from_pipeline_line("Summarizing batch 2/4…")
    assert stage_progress == (2, 0.5)
    assert label == "summarizing [2/4]…"


def test_status_from_pipeline_line_handles_failures():
    assert _status_from_pipeline_line("❌ Failed: boom") == ((3, 1.0), "Failed.")


def test_normalize_report_mode_label_returns_single_pass():
    assert (
        _normalize_report_mode(REPORT_MODE_LABEL_SINGLE_PASS) == REPORT_MODE_SINGLE_PASS
    )


def test_normalize_report_mode_value_returns_single_pass():
    assert _normalize_report_mode(REPORT_MODE_SINGLE_PASS) == REPORT_MODE_SINGLE_PASS


def test_normalize_report_mode_per_category():
    assert _normalize_report_mode("Per category summary") == REPORT_MODE_PER_CATEGORY
    assert _normalize_report_mode(None) == REPORT_MODE_PER_CATEGORY


def test_normalize_content_level_exact_labels():
    """Labels map to constants via exact match (no substring confusion)."""
    assert (
        _normalize_content_level(CONTENT_LEVEL_LABEL_MINIMAL) == CONTENT_LEVEL_MINIMAL
    )
    assert (
        _normalize_content_level(CONTENT_LEVEL_LABEL_SUMMARY) == CONTENT_LEVEL_SUMMARY
    )
    assert _normalize_content_level(CONTENT_LEVEL_LABEL_FULL) == CONTENT_LEVEL_FULL
