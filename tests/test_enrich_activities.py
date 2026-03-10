"""Tests for enrich_activities module."""

import pytest

from linkedin_api.enrich_activities import _is_comment_feed_url, enrich_activities
from linkedin_api.content_store import (
    save_content,
    load_metadata,
    has_metadata,
)


class TestIsCommentFeedUrl:
    def test_comment_urn_in_url(self):
        assert (
            _is_comment_feed_url(
                "https://linkedin.com/feed/update/urn:li:comment:(activity:123,456)"
            )
            is True
        )

    def test_post_urn_in_url(self):
        assert (
            _is_comment_feed_url("https://linkedin.com/feed/update/urn:li:activity:123")
            is False
        )


class TestEnrichSavesTimestamps:
    """Verify timestamp and post_created_at flow from activities into content store metadata."""

    @pytest.fixture(autouse=True)
    def use_tmp_data_dir(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LINKEDIN_DATA_DIR", str(tmp_path))

    def test_reaction_timestamp_and_post_created_saved_to_metadata(self):
        urn = "urn:li:ugcPost:123456"
        url = "https://www.linkedin.com/feed/update/urn:li:ugcPost:123456"
        ts_ms = 1700000000000
        post_created = "2024-01-15T10:30:00Z"

        save_content(urn, "x" * 100)
        assert not has_metadata(urn)

        activities = [
            {
                "post_urn": urn,
                "post_url": url,
                "urls": ["https://example.com"],
                "timestamp": ts_ms,
                "post_created_at": post_created,
            }
        ]
        enriched, count = enrich_activities(activities)
        assert count == 1

        meta = load_metadata(urn)
        assert meta is not None
        assert meta.get("reaction_created_at") == "2023-11-14T22:13:20+00:00"
        assert meta.get("post_created_at") == post_created

    def test_activities_without_timestamps_save_none(self):
        urn = "urn:li:ugcPost:789"
        save_content(urn, "x" * 100)

        activities = [
            {
                "post_urn": urn,
                "post_url": "https://linkedin.com/feed/update/urn:li:ugcPost:789",
            }
        ]
        enriched, count = enrich_activities(activities)
        assert count == 1

        meta = load_metadata(urn)
        assert meta is not None
        assert meta.get("reaction_created_at") in (None, "")
        assert meta.get("post_created_at") in (None, "")
