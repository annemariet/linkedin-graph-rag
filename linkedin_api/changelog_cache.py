"""
Persistent cache of changelog extraction data to avoid re-fetching from the LinkedIn API.

Cache is stored under get_data_dir() / "changelog_cache.json". Each run fetches only
new elements (since last_fetched_ms), merges with cache, and filters by the requested
period when collecting activities. Summarization already skips posts that have metadata.
"""

from __future__ import annotations

import json
from pathlib import Path

from linkedin_api.activity_csv import get_data_dir

CACHE_FILENAME = "changelog_cache.json"


def _cache_path() -> Path:
    return get_data_dir() / CACHE_FILENAME


def load_changelog_cache() -> dict | None:
    """Load cache: {last_fetched_ms: int, nodes: [...], relationships: [...]}. Returns None if missing/invalid."""
    path = _cache_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if (
            not isinstance(data, dict)
            or "nodes" not in data
            or "relationships" not in data
        ):
            return None
        return data
    except (json.JSONDecodeError, OSError):
        return None


def save_changelog_cache(data: dict) -> None:
    """Persist cache. data must have last_fetched_ms, nodes, relationships."""
    path = _cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _rel_key(r: dict) -> tuple:
    """Dedupe key for a relationship."""
    props = r.get("properties") or {}
    return (
        r.get("from") or r.get("startNode"),
        r.get("to") or r.get("endNode"),
        r.get("type"),
        props.get("timestamp"),
    )


def merge_extracted(
    existing: dict | None,
    new_nodes: list[dict],
    new_relationships: list[dict],
    last_fetched_ms: int,
) -> dict:
    """Merge new extraction into existing cache. Returns full cache dict."""
    nodes_by_id: dict[str, dict] = {}
    for n in existing.get("nodes", []) if existing else []:
        nid = n.get("id")
        if nid:
            nodes_by_id[nid] = n
    for n in new_nodes:
        nid = n.get("id")
        if nid:
            nodes_by_id[nid] = n

    seen_rels: set[tuple] = set()
    rels: list[dict] = []
    for r in existing.get("relationships", []) if existing else []:
        rn = {
            "type": r["type"],
            "from": r.get("from") or r.get("startNode"),
            "to": r.get("to") or r.get("endNode"),
            "properties": r.get("properties", {}),
        }
        k = _rel_key(rn)
        if k not in seen_rels:
            seen_rels.add(k)
            rels.append(rn)
    for r in new_relationships:
        rn = {
            "type": r.get("type"),
            "from": r.get("from") or r.get("startNode"),
            "to": r.get("to") or r.get("endNode"),
            "properties": r.get("properties", {}),
        }
        k = _rel_key(rn)
        if k not in seen_rels:
            seen_rels.add(k)
            rels.append(rn)

    return {
        "last_fetched_ms": last_fetched_ms,
        "nodes": list(nodes_by_id.values()),
        "relationships": rels,
    }
