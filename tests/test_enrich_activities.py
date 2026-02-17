"""Tests for enrich_activities module."""

from linkedin_api.enrich_activities import _is_comment_feed_url


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
