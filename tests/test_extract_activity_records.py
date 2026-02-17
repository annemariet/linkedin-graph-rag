"""Tests for ActivityRecord extraction from changelog elements."""

from linkedin_api.activity_csv import ActivityRecord, ActivityType
from linkedin_api.extract_graph_data import (
    extract_activity_records,
    records_to_neo4j_json,
)
from linkedin_api.utils.urns import build_comment_urn


# -- Fixtures (reuse activity shapes from existing tests) -------------------


def _reaction_element(post_urn="urn:li:ugcPost:111", actor="urn:li:person:abc"):
    return {
        "resourceName": "socialActions/likes",
        "actor": actor,
        "activity": {
            "root": post_urn,
            "reactionType": "LIKE",
            "created": {"time": 1700000000000},
        },
    }


def _post_element(
    post_urn="urn:li:share:222", author="urn:li:person:author1", content="Hello"
):
    return {
        "resourceName": "ugcPosts",
        "actor": author,
        "activity": {
            "id": post_urn,
            "author": author,
            "created": {"time": 1700000060000},
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": content},
                },
            },
        },
    }


def _repost_element(
    repost_urn="urn:li:share:333",
    original_urn="urn:li:ugcPost:444",
    reposter="urn:li:person:reposter",
):
    return {
        "resourceName": "ugcPosts",
        "actor": reposter,
        "activity": {
            "id": repost_urn,
            "author": "urn:li:person:original_author",
            "ugcOrigin": "RESHARE",
            "responseContext": {"parent": original_urn},
            "created": {"time": 1700000120000},
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {"shareCommentary": {"text": ""}},
            },
        },
    }


def _comment_element(
    post_urn="urn:li:ugcPost:555",
    comment_id="7410301301244284929",
    actor="urn:li:person:commenter",
    text="Great post!",
):
    return {
        "resourceName": "socialActions/comments",
        "actor": actor,
        "activity": {
            "id": comment_id,
            "object": post_urn,
            "message": {"text": text},
            "created": {"time": 1700000180000},
        },
    }


def _instant_repost_element(
    original="urn:li:share:666", actor="urn:li:person:reposter2"
):
    return {
        "resourceName": "instantReposts",
        "actor": actor,
        "activity": {
            "repostedContent": {"share": original},
            "created": {"time": 1700000240000},
        },
    }


# -- extract_activity_records -----------------------------------------------


class TestExtractActivityRecords:
    def test_reaction_produces_record(self):
        records = extract_activity_records([_reaction_element()])
        assert len(records) == 1
        r = records[0]
        assert r.activity_type == ActivityType.REACTION_TO_POST.value
        assert r.reaction_type == "LIKE"
        assert r.author_urn == "urn:li:person:abc"
        assert r.activity_urn == "urn:li:ugcPost:111"

    def test_post_produces_record(self):
        records = extract_activity_records([_post_element()])
        assert len(records) == 1
        r = records[0]
        assert r.activity_type == ActivityType.POST.value
        assert r.content == "Hello"
        assert r.author_urn == "urn:li:person:author1"

    def test_repost_produces_record(self):
        records = extract_activity_records([_repost_element()])
        assert len(records) == 1
        r = records[0]
        assert r.activity_type == ActivityType.REPOST.value
        assert r.author_urn == "urn:li:person:reposter"
        assert r.original_post_urn == "urn:li:ugcPost:444"

    def test_comment_produces_record(self):
        records = extract_activity_records([_comment_element()])
        assert len(records) == 1
        r = records[0]
        assert r.activity_type == ActivityType.COMMENT.value
        assert r.content == "Great post!"
        comment_urn = build_comment_urn("urn:li:ugcPost:555", "7410301301244284929")
        assert r.activity_urn == comment_urn
        assert r.parent_urn == "urn:li:ugcPost:555"

    def test_instant_repost_produces_record(self):
        records = extract_activity_records([_instant_repost_element()])
        assert len(records) == 1
        r = records[0]
        assert r.activity_type == ActivityType.INSTANT_REPOST.value
        assert r.author_urn == "urn:li:person:reposter2"
        assert r.activity_urn == "urn:li:share:666"

    def test_mixed_elements(self):
        elements = [
            _reaction_element(),
            _post_element(),
            _comment_element(),
            _instant_repost_element(),
        ]
        records = extract_activity_records(elements)
        assert len(records) == 4
        types = {r.activity_type for r in records}
        assert types == {
            ActivityType.REACTION_TO_POST.value,
            ActivityType.POST.value,
            ActivityType.COMMENT.value,
            ActivityType.INSTANT_REPOST.value,
        }

    def test_owner_propagated(self):
        records = extract_activity_records(
            [_post_element()], owner="urn:li:person:owner1"
        )
        assert records[0].owner == "urn:li:person:owner1"

    def test_delete_reaction_skipped(self):
        elem = _reaction_element()
        elem["method"] = "DELETE"
        records = extract_activity_records([elem])
        assert len(records) == 0

    def test_comment_like_under_post_resource_routes_to_comment(self):
        """When resourceName is ugcPosts but activity is comment-like, type is 'comment'."""
        element = {
            "resourceName": "ugcPosts",
            "actor": "urn:li:person:abc",
            "activity": {
                "id": "7410301301244284929",
                "object": "urn:li:ugcPost:7409540812340097024",
                "message": {"text": "A comment"},
                "created": {"time": 1766750428159},
            },
        }
        records = extract_activity_records([element])
        assert len(records) == 1
        assert records[0].activity_type == ActivityType.COMMENT.value

    def test_created_at_is_iso(self):
        records = extract_activity_records([_post_element()])
        assert "2023" in records[0].created_at  # epoch 1700000060000 -> 2023-*

    def test_time_is_epoch_string(self):
        records = extract_activity_records([_post_element()])
        assert records[0].time == "1700000060000"


# -- records_to_neo4j_json --------------------------------------------------


class TestRecordsToNeo4jJson:
    def test_post_record_produces_nodes_and_rels(self):
        rec = ActivityRecord(
            activity_type=ActivityType.POST.value,
            author_urn="urn:li:person:a1",
            activity_urn="urn:li:share:p1",
            post_url="https://linkedin.com/feed/update/urn:li:share:p1",
            content="Test content",
            time="1700000000000",
            created_at="2023-11-14T22:13:20",
        )
        data = records_to_neo4j_json([rec])
        assert data["statistics"]["posts"] == 1
        assert data["statistics"]["people"] == 1
        # Should produce IS_AUTHOR_OF relationship (new name)
        rel_types = [r["type"] for r in data["relationships"]]
        assert "IS_AUTHOR_OF" in rel_types

    def test_reaction_record_produces_reacted_to(self):
        rec = ActivityRecord(
            activity_type=ActivityType.REACTION_TO_POST.value,
            author_urn="urn:li:person:a1",
            activity_urn="urn:li:share:p1",
            reaction_type="LIKE",
            time="1700000000000",
            created_at="2023-11-14T22:13:20",
        )
        data = records_to_neo4j_json([rec])
        rel_types = [r["type"] for r in data["relationships"]]
        assert "REACTED_TO" in rel_types

    def test_repost_record_produces_reposts(self):
        rec = ActivityRecord(
            activity_type=ActivityType.REPOST.value,
            author_urn="urn:li:person:a1",
            activity_urn="urn:li:share:repost1",
            original_post_urn="urn:li:ugcPost:orig1",
            time="1700000000000",
            created_at="2023-11-14T22:13:20",
        )
        data = records_to_neo4j_json([rec])
        rel_types = [r["type"] for r in data["relationships"]]
        assert rel_types.count("REPOSTS") == 2  # Person->repost + repost->original

    def test_comment_record_produces_comments_on(self):
        rec = ActivityRecord(
            activity_type=ActivityType.COMMENT.value,
            author_urn="urn:li:person:a1",
            activity_urn="urn:li:comment:(ugcPost:p1,c1)",
            content="Nice!",
            parent_urn="urn:li:ugcPost:p1",
            time="1700000000000",
            created_at="2023-11-14T22:13:20",
        )
        data = records_to_neo4j_json([rec])
        rel_types = [r["type"] for r in data["relationships"]]
        assert "IS_AUTHOR_OF" in rel_types
        assert "COMMENTS_ON" in rel_types

    def test_uses_new_relationship_names(self):
        """Verify records_to_neo4j_json uses renamed relationships."""
        records = [
            ActivityRecord(
                activity_type=ActivityType.POST.value,
                author_urn="urn:li:person:a1",
                activity_urn="urn:li:share:p1",
                time="1700000000000",
            ),
            ActivityRecord(
                activity_type=ActivityType.REACTION_TO_POST.value,
                author_urn="urn:li:person:a2",
                activity_urn="urn:li:share:p1",
                reaction_type="LIKE",
                time="1700000000000",
            ),
        ]
        data = records_to_neo4j_json(records)
        rel_types = {r["type"] for r in data["relationships"]}
        # New names
        assert "IS_AUTHOR_OF" in rel_types
        assert "REACTED_TO" in rel_types
        # Old names should NOT appear
        assert "CREATES" not in rel_types
        assert "REACTS_TO" not in rel_types
