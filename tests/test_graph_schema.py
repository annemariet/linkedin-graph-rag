"""Tests for graph_schema module -- validates schema consistency."""

from linkedin_api.graph_schema import (
    NODE_TYPES,
    RELATIONSHIP_TYPES,
    PATTERNS,
    PHASE_A_RELATIONSHIP_TYPES,
    RELATIONSHIP_RENAMES,
    get_node_labels,
    get_pipeline_schema,
)


class TestNodeTypes:
    def test_all_have_label(self):
        for nt in NODE_TYPES:
            assert "label" in nt, f"Node type missing label: {nt}"
            assert isinstance(nt["label"], str)
            assert len(nt["label"]) > 0

    def test_all_have_description(self):
        for nt in NODE_TYPES:
            assert "description" in nt, f"Node type {nt['label']} missing description"

    def test_labels_are_unique(self):
        labels = [nt["label"] for nt in NODE_TYPES]
        assert len(labels) == len(set(labels)), f"Duplicate labels: {labels}"

    def test_expected_structural_types(self):
        labels = get_node_labels()
        for expected in ("Person", "Post", "Comment"):
            assert expected in labels, f"Missing structural node type: {expected}"

    def test_expected_enrichment_types(self):
        labels = get_node_labels()
        for expected in (
            "Resource",
            "Technology",
            "Concept",
            "Process",
            "Challenge",
            "Benefit",
            "Example",
        ):
            assert expected in labels, f"Missing enrichment node type: {expected}"


class TestRelationshipTypes:
    def test_no_duplicates(self):
        assert len(RELATIONSHIP_TYPES) == len(set(RELATIONSHIP_TYPES))

    def test_phase_a_subset(self):
        for rt in PHASE_A_RELATIONSHIP_TYPES:
            assert (
                rt in RELATIONSHIP_TYPES
            ), f"Phase A rel type {rt} not in RELATIONSHIP_TYPES"


class TestPatterns:
    def test_all_source_labels_defined(self):
        labels = get_node_labels()
        for src, rel, tgt in PATTERNS:
            assert (
                src in labels
            ), f"Unknown source label {src!r} in pattern ({src}, {rel}, {tgt})"

    def test_all_target_labels_defined(self):
        labels = get_node_labels()
        for src, rel, tgt in PATTERNS:
            assert (
                tgt in labels
            ), f"Unknown target label {tgt!r} in pattern ({src}, {rel}, {tgt})"

    def test_all_rel_types_defined(self):
        for src, rel, tgt in PATTERNS:
            assert (
                rel in RELATIONSHIP_TYPES
            ), f"Unknown rel type {rel!r} in pattern ({src}, {rel}, {tgt})"

    def test_no_duplicate_patterns(self):
        assert len(PATTERNS) == len(set(PATTERNS)), "Duplicate patterns found"

    def test_all_rel_types_used_in_at_least_one_pattern(self):
        used = {rel for _, rel, _ in PATTERNS}
        for rt in RELATIONSHIP_TYPES:
            assert rt in used, f"Relationship type {rt!r} not used in any pattern"


class TestRelationshipRenames:
    def test_old_names_not_in_current_types(self):
        """Old relationship names should not appear in the current schema."""
        for old_name in RELATIONSHIP_RENAMES:
            assert (
                old_name not in RELATIONSHIP_TYPES
            ), f"Old name {old_name!r} still in RELATIONSHIP_TYPES"

    def test_new_names_in_current_types(self):
        for new_name in RELATIONSHIP_RENAMES.values():
            assert (
                new_name in RELATIONSHIP_TYPES
            ), f"Rename target {new_name!r} not in RELATIONSHIP_TYPES"


class TestGetPipelineSchema:
    def test_returns_dict_with_required_keys(self):
        schema = get_pipeline_schema()
        assert "entities" in schema
        assert "relations" in schema
        assert "potential_schema" in schema

    def test_entities_match_node_types(self):
        schema = get_pipeline_schema()
        schema_labels = {e["label"] for e in schema["entities"]}
        defined_labels = get_node_labels()
        assert schema_labels == defined_labels

    def test_relations_match_relationship_types(self):
        schema = get_pipeline_schema()
        schema_rels = {r["label"] for r in schema["relations"]}
        assert schema_rels == set(RELATIONSHIP_TYPES)

    def test_potential_schema_matches_patterns(self):
        schema = get_pipeline_schema()
        assert schema["potential_schema"] == PATTERNS
