"""
Test extraction preview against saved fixtures.

Loads fixtures from outputs/review/fixtures/ (raw_element + expected_extracted)
and asserts extract_element_preview(raw_element)["extracted"] matches expected.
Skips if no fixtures exist (e.g. in CI without running the review UI).
"""

import json
from pathlib import Path

import pytest

from linkedin_api.extraction_preview import extract_element_preview

FIXTURES_DIR = (
    Path(__file__).resolve().parent.parent / "outputs" / "review" / "fixtures"
)


def _normalize_for_compare(data):
    """Normalize dict/list for comparison (e.g. sort keys, strip optional fields)."""
    if isinstance(data, dict):
        return {k: _normalize_for_compare(v) for k, v in sorted(data.items())}
    if isinstance(data, list):
        return [_normalize_for_compare(x) for x in data]
    return data


def _fixture_ids():
    if not FIXTURES_DIR.exists():
        return []
    return [f.stem for f in FIXTURES_DIR.glob("*.json")]


@pytest.mark.parametrize("element_id", _fixture_ids())
def test_extraction_matches_fixture(element_id):
    """For each fixture, extracted output should match expected_extracted (after corrections)."""
    path = FIXTURES_DIR / f"{element_id}.json"
    if not path.exists():
        pytest.skip(f"Fixture {path} not found")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    raw_element = data.get("raw_element")
    expected = data.get("expected_extracted")
    if not raw_element or expected is None:
        pytest.skip(f"Fixture {element_id} missing raw_element or expected_extracted")
    result = extract_element_preview(raw_element)
    got = result.get("extracted", {})
    # Compare normalized (ignore trace in expected; we only lock extracted shape/values)
    expected_norm = _normalize_for_compare(expected)
    got_norm = _normalize_for_compare(got)
    assert got_norm == expected_norm, (
        f"Fixture {element_id}: extracted does not match expected. "
        f"Got keys: {sorted(got.keys())}, expected keys: {sorted(expected.keys())}"
    )
