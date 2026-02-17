"""Tests for enrich_graph module (import and schema validation only)."""


def test_module_importable():
    from linkedin_api.enrich_graph import (  # noqa: F401
        create_kg_pipeline,
        get_posts_needing_enrichment,
        mark_as_enriched,
        enrich_graph,
    )


def test_pipeline_schema_valid():
    from linkedin_api.graph_schema import get_pipeline_schema

    schema = get_pipeline_schema()
    assert "entities" in schema
    assert "relations" in schema
    assert "potential_schema" in schema
    assert len(schema["entities"]) >= 10
    assert len(schema["relations"]) >= 10
