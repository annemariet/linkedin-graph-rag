"""Tests for summarize_activity module."""

import json
import tempfile
from pathlib import Path

import pytest

from linkedin_api.summarize_activity import (
    ActivityRecord,
    _parse_last,
    collect_activities,
    load_from_cache,
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


class TestLoadFromCache:
    def test_empty_dir(self, tmp_path):
        data = load_from_cache(path=tmp_path)
        assert data["nodes"] == []
        assert data["relationships"] == []

    def test_valid_json(self, tmp_path):
        neo4j = {
            "nodes": [
                {"id": "urn:li:person:me", "labels": ["Person"], "properties": {}},
                {"id": "urn:li:activity:123", "labels": ["Post"], "properties": {}},
            ],
            "relationships": [
                {
                    "type": "REACTS_TO",
                    "startNode": "urn:li:person:me",
                    "endNode": "urn:li:activity:123",
                    "properties": {"timestamp": 1700000000000},
                },
            ],
        }
        fp = tmp_path / "neo4j_data_test.json"
        fp.write_text(json.dumps(neo4j))
        data = load_from_cache(path=fp)
        assert len(data["nodes"]) == 2
        assert len(data["relationships"]) == 1
        assert data["relationships"][0]["from"] == "urn:li:person:me"
        assert data["relationships"][0]["to"] == "urn:li:activity:123"


class TestCollectActivities:
    def test_reactions(self):
        data = {
            "nodes": [
                {"id": "urn:li:person:me", "labels": ["Person"], "properties": {}},
                {
                    "id": "urn:li:activity:123",
                    "labels": ["Post"],
                    "properties": {
                        "content": "Hello",
                        "extracted_urls": ["https://x.com"],
                    },
                },
            ],
            "relationships": [
                {
                    "type": "REACTS_TO",
                    "from": "urn:li:person:me",
                    "to": "urn:li:activity:123",
                    "properties": {"timestamp": 1700000000000},
                },
            ],
        }
        records = collect_activities(data, types={"reaction"})
        assert len(records) == 1
        assert records[0].post_urn == "urn:li:activity:123"
        assert records[0].content == "Hello"
        assert records[0].urls == ["https://x.com"]
        assert records[0].interaction_type == "reaction"

    def test_filters_by_type(self):
        data = {
            "nodes": [
                {"id": "urn:li:person:me", "labels": ["Person"], "properties": {}},
                {"id": "urn:li:activity:123", "labels": ["Post"], "properties": {}},
            ],
            "relationships": [
                {
                    "type": "REACTS_TO",
                    "from": "urn:li:person:me",
                    "to": "urn:li:activity:123",
                    "properties": {"timestamp": 1700000000000},
                },
            ],
        }
        records = collect_activities(data, types={"repost"})
        assert len(records) == 0
