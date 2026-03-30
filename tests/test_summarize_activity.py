"""Tests for summarize_activity module."""

import pytest

from linkedin_api.activity_csv import (
    ActivityRecord,
    ActivityType,
    append_records_csv,
    make_activity_id,
)
from linkedin_api.summarize_activity import (
    _parse_last,
    collect_from_csv,
    load_activity_dicts_from_csv,
    summarization_record_to_activity_dict,
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
            content="Hello",
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
        records = collect_from_csv(csv_path=csv_with_reaction)
        assert len(records) == 1
        assert records[0].post_urn == "urn:li:activity:123"
        assert records[0].content == "Hello"
        assert records[0].interaction_type == "reaction"
        assert records[0].reaction_type == "INTEREST"
        assert records[0].created_at == "2023-11-14T22:13:20+0000"

    def test_empty_csv(self, tmp_path):
        path = tmp_path / "empty.csv"
        path.touch()
        records = collect_from_csv(csv_path=path)
        assert records == []

    def test_summarization_record_to_activity_dict(self, csv_with_reaction):
        records = collect_from_csv(csv_path=csv_with_reaction)
        d = summarization_record_to_activity_dict(records[0])
        assert d["post_urn"] == "urn:li:activity:123"
        assert d["timestamp"] == 1700000000000
        assert d["created_at"] == "2023-11-14T22:13:20+0000"

    def test_load_activity_dicts_from_csv(self, csv_with_reaction):
        rows = load_activity_dicts_from_csv(csv_with_reaction)
        assert len(rows) == 1
        assert rows[0]["activity_id"]
        assert rows[0]["post_id"] == "123"
