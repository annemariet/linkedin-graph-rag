"""Tests for linkedin_snowflake module."""

from linkedin_api.utils.linkedin_snowflake import (
    post_created_at_from_urn,
    timestamp_ms_from_linkedin_id,
)


class TestTimestampFromLinkedInId:
    def test_extracts_timestamp_from_19_digit_id(self):
        # From Ollie-Boyd: first 41 bits of 7206271470342131712
        ts = timestamp_ms_from_linkedin_id("7206271470342131712")
        assert ts is not None
        assert 1600000000000 < ts < 1900000000000  # 2020–2030

    def test_returns_none_for_invalid(self):
        assert timestamp_ms_from_linkedin_id("") is None
        assert timestamp_ms_from_linkedin_id("abc") is None
        assert timestamp_ms_from_linkedin_id("123") is None  # too short


class TestPostCreatedAtFromUrn:
    def test_ugc_post_urn(self):
        result = post_created_at_from_urn("urn:li:ugcPost:7398404729531285504")
        assert result is not None
        assert "T" in result
        assert result.startswith("20")

    def test_activity_urn(self):
        result = post_created_at_from_urn("urn:li:activity:7206271470342131712")
        assert result is not None

    def test_comment_urn_returns_none(self):
        assert post_created_at_from_urn("urn:li:comment:(activity:123,456)") is None
