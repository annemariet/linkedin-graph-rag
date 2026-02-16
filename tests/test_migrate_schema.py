"""Tests for migrate_schema module (logic only, no Neo4j)."""

from linkedin_api.graph_schema import RELATIONSHIP_RENAMES


def test_all_renames_map_to_valid_targets():
    from linkedin_api.graph_schema import RELATIONSHIP_TYPES

    for old, new in RELATIONSHIP_RENAMES.items():
        assert new in RELATIONSHIP_TYPES
        assert old not in RELATIONSHIP_TYPES


def test_renames_are_complete():
    """All three historical names are covered."""
    assert "CREATES" in RELATIONSHIP_RENAMES
    assert "REACTS_TO" in RELATIONSHIP_RENAMES
    assert "ON_POST" in RELATIONSHIP_RENAMES


def test_migrate_relationship_importable():
    from linkedin_api.migrate_schema import migrate_relationship  # noqa: F401
