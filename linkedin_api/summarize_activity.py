#!/usr/bin/env python3
"""
Collect activities (reactions, reposts, comments) for period-based summarization.

Supports:
- Live: fetch from Portability API with --last 7d|14d|30d
- Cache: load from outputs/neo4j_data_*.json with --from-cache

Output: list of {post_urn, content, urls, interaction_type, timestamp}
for use by summarization and linked-resource pipelines.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from linkedin_api.extract_graph_data import (
    extract_entities_and_relationships,
    get_all_post_activities,
)
from linkedin_api.extract_resources import extract_urls_from_text

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs"


@dataclass
class ActivityRecord:
    """Single activity (reaction, repost, or comment) for summarization."""

    post_urn: str
    content: str
    urls: list[str]
    interaction_type: Literal["reaction", "repost", "comment"]
    timestamp: int | None
    comment_text: str = ""
    comment_urn: str = ""


def _parse_last(value: str) -> int | None:
    """Convert '7d', '14d', '30d' to start_time in epoch milliseconds."""
    if not value or len(value) < 2:
        return None
    try:
        n = int(value[:-1])
    except ValueError:
        return None
    unit = value[-1].lower()
    if unit == "d":
        delta = timedelta(days=n)
    elif unit == "w":
        delta = timedelta(weeks=n)
    elif unit == "m":
        delta = timedelta(days=n * 30)
    else:
        return None
    cutoff = datetime.now(timezone.utc) - delta
    return int(cutoff.timestamp() * 1000)


def _normalize_relationships(data: dict) -> list[dict]:
    """Ensure relationships use 'from' and 'to' keys."""
    rels = data.get("relationships", [])
    out = []
    for r in rels:
        out.append(
            {
                "type": r["type"],
                "from": r.get("from") or r.get("startNode"),
                "to": r.get("to") or r.get("endNode"),
                "properties": r.get("properties", {}),
            }
        )
    return out


def _nodes_by_id(data: dict) -> dict[str, dict]:
    """Index nodes by id for lookup."""
    by_id = {}
    for node in data.get("nodes", []):
        nid = node.get("id")
        if nid:
            by_id[nid] = node
    return by_id


def _in_time_range(ts: int | None, start_ms: int | None, end_ms: int | None) -> bool:
    if ts is None:
        return True
    if start_ms is not None and ts < start_ms:
        return False
    if end_ms is not None and ts > end_ms:
        return False
    return True


def load_from_cache(
    path: Path | None = None,
    start_ms: int | None = None,
    end_ms: int | None = None,
) -> dict:
    """
    Load extraction data from cached neo4j_data JSON.

    Args:
        path: Specific file, or None to use latest in outputs/
        start_ms: Optional start time filter (epoch ms) for relationships
        end_ms: Optional end time filter (epoch ms) for relationships

    Returns:
        Dict with nodes, relationships (normalized with from/to)
    """
    if path:
        files = [path] if path.is_file() else []
    else:
        pattern = "neo4j_data_*.json"
        files = sorted(
            OUTPUT_DIR.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True
        )
    if not files:
        return {"nodes": [], "relationships": []}

    all_nodes: dict[str, dict] = {}
    all_rels: list[dict] = []
    for fp in files:
        raw = json.loads(fp.read_text())
        for node in raw.get("nodes", []):
            all_nodes[node.get("id")] = node
        for r in raw.get("relationships", []):
            rel = {
                "type": r["type"],
                "from": r.get("from") or r.get("startNode"),
                "to": r.get("to") or r.get("endNode"),
                "properties": r.get("properties", {}),
            }
            ts = rel["properties"].get("timestamp")
            if _in_time_range(ts, start_ms, end_ms):
                all_rels.append(rel)
    return {"nodes": list(all_nodes.values()), "relationships": all_rels}


def collect_from_live(
    last: str,
    types: set[str],
    verbose: bool = True,
) -> dict:
    """
    Fetch from API and extract entities. Returns same structure as load_from_cache.
    """
    start_time = _parse_last(last)
    if start_time is None:
        raise ValueError(f"Invalid --last value; use e.g. 7d, 14d, 30d")
    elements = get_all_post_activities(start_time=start_time, verbose=verbose)
    data = extract_entities_and_relationships(elements)
    rels = _normalize_relationships(data)
    return {"nodes": data["nodes"], "relationships": rels}


def _infer_user_actor(
    relationships: list[dict], nodes_by_id: dict[str, dict]
) -> str | None:
    """Infer the current user's URN from REACTS_TO (actor is always the user)."""
    for r in relationships:
        if r["type"] == "REACTS_TO":
            actor = r["from"]
            if actor and actor.startswith("urn:li:person:"):
                return actor
    return None


def collect_activities(
    data: dict,
    types: set[Literal["reaction", "repost", "comment"]] | None = None,
    start_ms: int | None = None,
    end_ms: int | None = None,
) -> list[ActivityRecord]:
    """
    Extract activity records from extraction data (live or cached).

    Args:
        data: From load_from_cache or collect_from_live
        types: Include reaction, repost, comment (default: all)
        start_ms, end_ms: Optional time bounds

    Returns:
        List of ActivityRecord, one per unique (post_urn, interaction_type)
    """
    types = types or {"reaction", "repost", "comment"}
    nodes_by_id = _nodes_by_id(data)
    relationships = _normalize_relationships(data)
    user_actor = _infer_user_actor(relationships, nodes_by_id)
    if not user_actor:
        return []

    seen: set[tuple[str, str]] = set()
    records: list[ActivityRecord] = []

    def add_record(
        post_urn: str,
        content: str,
        urls: list[str],
        interaction_type: str,
        timestamp: int | None,
        comment_text: str = "",
        comment_urn: str = "",
    ):
        key = (post_urn, interaction_type)
        if key in seen:
            return
        if not _in_time_range(timestamp, start_ms, end_ms):
            return
        seen.add(key)
        records.append(
            ActivityRecord(
                post_urn=post_urn,
                content=content,
                urls=urls,
                interaction_type=interaction_type,
                timestamp=timestamp,
                comment_text=comment_text,
                comment_urn=comment_urn,
            )
        )

    # Reactions: (user)-[:REACTS_TO]->(post)
    if "reaction" in types:
        for r in relationships:
            if r["type"] != "REACTS_TO" or r["from"] != user_actor:
                continue
            post_urn = r["to"]
            props = r["properties"]
            ts = props.get("timestamp")
            post_node = nodes_by_id.get(post_urn, {})
            post_props = post_node.get("properties", {})
            content = post_props.get("content", "")
            urls = post_props.get("extracted_urls", [])
            if content and not urls:
                urls = extract_urls_from_text(content)
            add_record(post_urn, content, urls, "reaction", ts)

    # Reposts: (user)-[:REPOSTS]->(repost_share_post); original in original_post_urn
    if "repost" in types:
        for r in relationships:
            if r["type"] != "REPOSTS":
                continue
            from_urn = r["from"]
            to_urn = r["to"]
            if from_urn != user_actor:
                continue
            repost_node = nodes_by_id.get(to_urn, {})
            repost_props = repost_node.get("properties", {})
            original_urn = repost_props.get("original_post_urn")
            target_urn = original_urn or to_urn
            content = repost_props.get("content", "")
            urls = repost_props.get("extracted_urls", [])
            if content and not urls:
                urls = extract_urls_from_text(content)
            ts = repost_props.get("timestamp")
            if not content and original_urn:
                orig_node = nodes_by_id.get(original_urn, {})
                orig_props = orig_node.get("properties", {})
                content = orig_props.get("content", "")
                if not urls:
                    urls = orig_props.get(
                        "extracted_urls", []
                    ) or extract_urls_from_text(content)
            add_record(target_urn, content, urls, "repost", ts)

    # Comments: (user)-[:CREATES]->(comment)-[:COMMENTS_ON]->(post)
    if "comment" in types:
        user_comments = [
            r["to"]
            for r in relationships
            if r["type"] == "CREATES" and r["from"] == user_actor
        ]
        for comment_urn in user_comments:
            for r in relationships:
                if r["type"] != "COMMENTS_ON" or r["from"] != comment_urn:
                    continue
                post_urn = r["to"]
                comment_node = nodes_by_id.get(comment_urn, {})
                comment_props = comment_node.get("properties", {})
                comment_text = comment_props.get("text", "")
                ts = comment_props.get("timestamp")
                urls = comment_props.get("extracted_urls", [])
                if comment_text and not urls:
                    urls = extract_urls_from_text(comment_text)
                post_node = nodes_by_id.get(post_urn, {})
                post_props = post_node.get("properties", {})
                content = post_props.get("content", "")
                if not urls and content:
                    urls = post_props.get(
                        "extracted_urls", []
                    ) or extract_urls_from_text(content)
                add_record(
                    post_urn,
                    content,
                    urls,
                    "comment",
                    ts,
                    comment_text=comment_text,
                    comment_urn=comment_urn,
                )

    return records


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Collect activities for period-based summarization (reactions, reposts, comments)."
    )
    parser.add_argument(
        "--last",
        metavar="Nd",
        help="Fetch from API: last N days/weeks (e.g. 7d, 14d, 30d)",
    )
    parser.add_argument(
        "--from-cache",
        action="store_true",
        help="Load from outputs/neo4j_data_*.json instead of API. Use with --last to filter by period.",
    )
    parser.add_argument(
        "--types",
        default="reaction,repost,comment",
        help="Comma-separated: reaction, repost, comment (default: all)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Write JSON output to file",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Less verbose output",
    )
    args = parser.parse_args()

    if not args.last and not args.from_cache:
        parser.error("Specify --last or --from-cache")
    if args.last and not args.from_cache:
        pass  # Live API fetch
    elif args.from_cache:
        pass  # Cache; --last optional to filter within cached data

    types_set = {t.strip() for t in args.types.split(",") if t.strip()}
    start_ms = None
    end_ms = None
    if args.last:
        start_ms = _parse_last(args.last)
        if start_ms is None:
            parser.error(f"Invalid --last '{args.last}'; use e.g. 7d, 14d, 30d")
        end_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    # For --from-cache with --last: filter cached data by period (optional)
    cache_start = start_ms if args.from_cache else None
    cache_end = end_ms if args.from_cache else None

    if args.from_cache:
        data = load_from_cache(start_ms=cache_start, end_ms=cache_end)
        if not data["nodes"]:
            print("No cached neo4j_data_*.json found in outputs/")
            return 1
        print(
            f"Loaded {len(data['nodes'])} nodes, {len(data['relationships'])} "
            f"relationships from cache"
        )
    else:
        data = collect_from_live(args.last, types_set, verbose=not args.quiet)

    records = collect_activities(
        data, types=types_set, start_ms=start_ms, end_ms=end_ms
    )
    print(f"Collected {len(records)} activities")

    out = [
        {
            "post_urn": r.post_urn,
            "content": r.content,
            "urls": r.urls,
            "interaction_type": r.interaction_type,
            "timestamp": r.timestamp,
        }
        for r in records
    ]
    if args.output:
        args.output.write_text(json.dumps(out, indent=2))
        print(f"Wrote {args.output}")
    else:
        print(json.dumps(out[:5], indent=2))
        if len(out) > 5:
            print(f"... and {len(out) - 5} more")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
