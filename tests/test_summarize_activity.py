"""Tests for summarize_activity module."""

import pytest

from linkedin_api.activity_csv import (
    ActivityRecord,
    ActivityType,
    append_records_csv,
    load_records_csv,
    make_activity_id,
)
from linkedin_api.enriched_record import EnrichedRecord
from linkedin_api.summarize_activity import (
    _parse_last,
    collect_from_csv,
)


class TestParseLast:
    def test_7d(self):
        ts = _parse_last("7d")
        assert ts is not None
        from datetime import datetime, timedelta, timezone

        expected = datetime.now(timezone.utc) - timedelta(days=7)
        assert abs(ts / 1000 - expected.timestamp()) < 60

    def test_14d(self):
        assert _parse_last("14d") is not None

    def test_30d(self):
        assert _parse_last("30d") is not None

    def test_invalid(self):
        assert _parse_last("") is None
        assert _parse_last("x") is None
        assert _parse_last("7") is None


class TestCollectFromCsv:
    @pytest.fixture
    def csv_with_reaction(self, tmp_path):
        rec = ActivityRecord(
            owner="urn:li:person:me",
            activity_type=ActivityType.REACTION_TO_POST.value,
            time="1700000000000",
            reaction_type="INTEREST",
            author_urn="urn:li:person:me",
            activity_urn="urn:li:activity:123",
            post_id="123",
            post_url="https://www.linkedin.com/feed/update/urn:li:activity:123",
            content="",
            parent_urn="",
            original_post_urn="",
            activity_id=make_activity_id(
                "123", "reaction_to_post", "1700000000000", "urn:li:activity:123"
            ),
            created_at="2023-11-14T22:13:20+0000",
        )
        path = tmp_path / "activities.csv"
        append_records_csv([rec], path=path)
        return path

    def test_reactions(self, csv_with_reaction):
        rows = collect_from_csv(csv_path=csv_with_reaction)
        assert len(rows) == 1
        assert rows[0].post_urn == "urn:li:activity:123"
        assert rows[0].content == ""
        assert rows[0].interaction_type == "reaction"
        assert rows[0].reaction_type == "INTEREST"
        assert rows[0].created_at == "2023-11-14T22:13:20+0000"

    def test_empty_csv(self, tmp_path):
        path = tmp_path / "empty.csv"
        path.touch()
        records = collect_from_csv(csv_path=path)
        assert records == []

    def test_from_activity_record_matches_collect(self, csv_with_reaction):
        ar = load_records_csv(csv_with_reaction)[0]
        expected = EnrichedRecord.from_activity_record(ar)
        rows = collect_from_csv(csv_path=csv_with_reaction)
        assert rows == [expected]

    def test_post_row_interaction_type_is_post(self, tmp_path):
        rec = ActivityRecord(
            owner="urn:li:person:me",
            activity_type=ActivityType.POST.value,
            time="1700000000000",
            reaction_type="",
            author_urn="urn:li:person:me",
            activity_urn="urn:li:ugcPost:999",
            post_id="999",
            post_url="https://www.linkedin.com/feed/update/urn:li:ugcPost:999",
            content="Original post body from API.",
            parent_urn="",
            original_post_urn="",
            activity_id=make_activity_id(
                "999", "post", "1700000000000", "urn:li:ugcPost:999"
            ),
            created_at="",
        )
        path = tmp_path / "activities.csv"
        append_records_csv([rec], path=path)
        rows = collect_from_csv(csv_path=path)
        assert len(rows) == 1
        assert rows[0].interaction_type == "post"
        assert rows[0].content == "Original post body from API."
