"""Tests for build_graph CSV loading (no Neo4j required -- tests conversion logic)."""

from linkedin_api.activity_csv import ActivityRecord
from linkedin_api.build_graph import _records_to_nodes_and_rels
from linkedin_api.graph_schema import PHASE_A_RELATIONSHIP_TYPES


def _make_record(**kwargs):
    return ActivityRecord(**kwargs)


class TestRecordsToNodesAndRels:
    def test_post_creates_person_and_post_nodes(self):
        rec = _make_record(
            activity_type="post",
            author_urn="urn:li:person:a1",
            activity_urn="urn:li:share:p1",
            post_url="https://linkedin.com/feed/update/urn:li:share:p1",
            content="Hello",
            time="1700000000000",
            created_at="2023-11-14T22:13:20",
        )
        nodes, rels = _records_to_nodes_and_rels([rec])
        labels = [n["labels"][0] for n in nodes]
        assert "Person" in labels
        assert "Post" in labels
        assert any(r["type"] == "IS_AUTHOR_OF" for r in rels)

    def test_reaction_creates_reacted_to(self):
        rec = _make_record(
            activity_type="reaction_to_post",
            author_urn="urn:li:person:a1",
            activity_urn="urn:li:share:p1",
            reaction_type="LIKE",
            time="1700000000000",
        )
        nodes, rels = _records_to_nodes_and_rels([rec])
        assert any(r["type"] == "REACTED_TO" for r in rels)

    def test_comment_creates_comments_on_and_is_author_of(self):
        rec = _make_record(
            activity_type="comment",
            author_urn="urn:li:person:a1",
            activity_urn="urn:li:comment:(ugcPost:p1,c1)",
            content="Nice!",
            parent_urn="urn:li:ugcPost:p1",
            time="1700000000000",
        )
        nodes, rels = _records_to_nodes_and_rels([rec])
        rel_types = [r["type"] for r in rels]
        assert "IS_AUTHOR_OF" in rel_types
        assert "COMMENTS_ON" in rel_types

    def test_repost_creates_two_reposts_rels(self):
        rec = _make_record(
            activity_type="repost",
            author_urn="urn:li:person:a1",
            activity_urn="urn:li:share:r1",
            original_post_urn="urn:li:ugcPost:orig1",
            time="1700000000000",
        )
        nodes, rels = _records_to_nodes_and_rels([rec])
        reposts = [r for r in rels if r["type"] == "REPOSTS"]
        assert len(reposts) == 2

    def test_instant_repost(self):
        rec = _make_record(
            activity_type="instant_repost",
            author_urn="urn:li:person:a1",
            activity_urn="urn:li:share:orig1",
            time="1700000000000",
        )
        nodes, rels = _records_to_nodes_and_rels([rec])
        assert any(r["type"] == "REPOSTS" for r in rels)

    def test_all_rel_types_are_phase_a(self):
        """Every relationship produced must be in PHASE_A_RELATIONSHIP_TYPES."""
        records = [
            _make_record(
                activity_type="post",
                author_urn="urn:li:person:a1",
                activity_urn="urn:li:share:p1",
                time="1",
            ),
            _make_record(
                activity_type="reaction_to_post",
                author_urn="urn:li:person:a2",
                activity_urn="urn:li:share:p1",
                reaction_type="LIKE",
                time="2",
            ),
            _make_record(
                activity_type="comment",
                author_urn="urn:li:person:a3",
                activity_urn="urn:li:comment:(ugcPost:p1,c1)",
                parent_urn="urn:li:ugcPost:p1",
                time="3",
            ),
            _make_record(
                activity_type="repost",
                author_urn="urn:li:person:a4",
                activity_urn="urn:li:share:r1",
                original_post_urn="urn:li:share:p1",
                time="4",
            ),
            _make_record(
                activity_type="instant_repost",
                author_urn="urn:li:person:a5",
                activity_urn="urn:li:share:p1",
                time="5",
            ),
        ]
        _, rels = _records_to_nodes_and_rels(records)
        for rel in rels:
            assert (
                rel["type"] in PHASE_A_RELATIONSHIP_TYPES
            ), f"Unexpected rel type: {rel['type']}"

    def test_no_old_relationship_names(self):
        records = [
            _make_record(
                activity_type="post",
                author_urn="urn:li:person:a1",
                activity_urn="urn:li:share:p1",
                time="1",
            ),
            _make_record(
                activity_type="reaction_to_post",
                author_urn="urn:li:person:a2",
                activity_urn="urn:li:share:p1",
                reaction_type="LIKE",
                time="2",
            ),
        ]
        _, rels = _records_to_nodes_and_rels(records)
        rel_types = {r["type"] for r in rels}
        assert "CREATES" not in rel_types
        assert "REACTS_TO" not in rel_types
        assert "ON_POST" not in rel_types

    def test_dedup_person_nodes(self):
        records = [
            _make_record(
                activity_type="post",
                author_urn="urn:li:person:a1",
                activity_urn="urn:li:share:p1",
                time="1",
            ),
            _make_record(
                activity_type="reaction_to_post",
                author_urn="urn:li:person:a1",
                activity_urn="urn:li:share:p2",
                reaction_type="LIKE",
                time="2",
            ),
        ]
        nodes, _ = _records_to_nodes_and_rels(records)
        person_nodes = [n for n in nodes if "Person" in n["labels"]]
        assert len(person_nodes) == 1
