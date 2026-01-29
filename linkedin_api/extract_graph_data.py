#!/usr/bin/env python3
"""
Extract graph data from LinkedIn changelog API.

Fetches post-related activities from LinkedIn Member Data Portability API
and extracts entities (Posts, People, Comments, Reactions) and relationships
for import into Neo4j.

Output: Saves neo4j_data_*.json file with nodes and relationships.

This is Step 1 of the graph building workflow:
1. extract_graph_data.py → Fetch and extract data to JSON
2. build_graph.py → Load JSON into Neo4j and enrich
"""

import argparse
import json
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from linkedin_api.utils.changelog import (
    fetch_changelog_data,
    get_max_processed_at,
    save_last_processed_timestamp,
)
from linkedin_api.utils.summaries import print_resource_summary, summarize_resources
from linkedin_api.utils.urns import (
    extract_urn_id,
    urn_to_post_url,
    build_comment_urn,
    comment_urn_to_post_url,
    parse_comment_urn,
)
from linkedin_api.analyze_activity import (
    extract_statistics,
    print_statistics,
    save_statistics,
)
from linkedin_api.extract_resources import extract_urls_from_text

# Resource type constants
RESOURCE_REACTIONS = "socialActions/likes"
RESOURCE_COMMENTS = "socialActions/comments"
RESOURCE_POSTS = "ugcPosts"
RESOURCE_POST = "ugcPost"
RESOURCE_INSTANT_REPOSTS = "instantReposts"

# Output directory
OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)


def format_timestamp(timestamp):
    """Format timestamp in milliseconds to ISO string."""
    if not timestamp:
        return None
    return datetime.fromtimestamp(timestamp / 1000).isoformat()


def create_person_node(person_urn, people):
    """Create a Person node if it doesn't exist."""
    if not person_urn or not person_urn.startswith("urn:li:person:"):
        return None

    if person_urn in people:
        return person_urn

    person_id = extract_urn_id(person_urn)
    if not person_id:
        return None

    people[person_urn] = {
        "id": person_urn,
        "label": "Person",
        "properties": {
            "urn": person_urn,
            "person_id": person_id,
        },
    }
    return person_urn


def create_post_node(post_urn, posts, additional_props=None):
    """Create a Post node if it doesn't exist."""
    if not post_urn or post_urn in posts:
        return post_urn

    post_id = extract_urn_id(post_urn)
    if not post_id:
        return None

    props = {
        "urn": post_urn,
        "post_id": post_id,
        "url": urn_to_post_url(post_urn) or "",
    }
    if additional_props:
        props.update(additional_props)

    posts[post_urn] = {
        "id": post_urn,
        "label": "Post",
        "properties": props,
    }
    return post_urn


def extract_actor(element, activity):
    """Extract actor URN from element or activity."""
    return element.get("actor", "") or activity.get("actor", "")


def _extract_post_urn_for_reaction(element, activity):
    """Extract the post/comment URN for a reaction from available fields."""
    post_urn = activity.get("root") or activity.get("object", "")
    if post_urn:
        return post_urn

    resource_id = element.get("resourceId", "")
    if isinstance(resource_id, str) and resource_id.startswith("urn:li:"):
        return resource_id

    resource_uri = element.get("resourceUri", "")
    if isinstance(resource_uri, str) and resource_uri:
        # Example: /socialActions/urn:li:activity:123/likes/urn:li:person:abc
        for part in resource_uri.split("/"):
            if part.startswith("urn:li:"):
                return part

    reaction_urn = activity.get("$URN") or activity.get("urn") or ""
    if isinstance(reaction_urn, str) and reaction_urn.startswith("urn:li:reaction:("):
        inner = reaction_urn[len("urn:li:reaction:(") :].rstrip(")")
        parts = [p.strip() for p in inner.split(",")]
        if len(parts) == 2 and parts[1].startswith("urn:li:"):
            return parts[1]

    return ""


def _is_delete_action(element):
    """Check whether the changelog element represents a delete action."""
    method = element.get("method") or element.get("methodName")
    return str(method).upper() == "DELETE"


def _remove_reaction_relationship(relationships, actor, post_urn):
    """Remove existing reaction relationships for an actor/post pair."""
    if not actor or not post_urn:
        return 0
    before_count = len(relationships)
    relationships[:] = [
        rel
        for rel in relationships
        if not (
            rel.get("type") == "REACTS_TO"
            and rel.get("from") == actor
            and rel.get("to") == post_urn
        )
    ]
    return before_count - len(relationships)


def _maybe_build_parent_comment_urn(post_urn, value):
    """Return a parent comment URN from a raw value when possible."""
    if not value:
        return None
    if isinstance(value, str):
        if value.startswith("urn:li:comment:"):
            return value
        if value.isdigit():
            return build_comment_urn(post_urn, value)
    return None


def _extract_parent_comment_urn(activity, response_context, post_urn):
    """Extract parent comment URN from activity/response context."""
    for container in (response_context, activity):
        if not isinstance(container, dict):
            continue
        for key in (
            "parent",
            "parentComment",
            "parentCommentUrn",
            "parentCommentURN",
            "parentCommentId",
            "parentCommentID",
        ):
            if key in container:
                parent_urn = _maybe_build_parent_comment_urn(post_urn, container[key])
                if parent_urn:
                    return parent_urn
    return None


def process_reaction(
    element, activity, people, posts, relationships, skipped_by_reason
):
    """Process a reaction element and update entities/relationships."""
    resource_name = element.get("resourceName", "")
    post_urn = _extract_post_urn_for_reaction(element, activity)
    reaction_type = activity.get("reactionType", "UNKNOWN")
    actor = extract_actor(element, activity)
    is_delete = _is_delete_action(element)

    if not post_urn:
        skipped_by_reason[f"reaction_no_post_urn_{resource_name}"] += 1
        return
    if not actor:
        skipped_by_reason[f"reaction_no_actor_{resource_name}"] += 1
        return

    if is_delete:
        removed = _remove_reaction_relationship(relationships, actor, post_urn)
        if removed:
            print(f"   🗑️  Removed {removed} reaction(s) for {actor} → {post_urn}")
        return

    timestamp = activity.get("created", {}).get("time")

    create_post_node(post_urn, posts)
    create_person_node(actor, people)

    relationships.append(
        {
            "type": "REACTS_TO",
            "from": actor,
            "to": post_urn,
            "properties": {
                "reaction_type": reaction_type,
                "timestamp": timestamp,
                "created_at": format_timestamp(timestamp),
            },
        }
    )


def process_post(element, activity, people, posts, relationships, skipped_by_reason):
    """Process a post element and update entities/relationships."""
    resource_name = element.get("resourceName", "")
    post_urn = activity.get("id", "")

    if not post_urn:
        skipped_by_reason[f"post_no_id_{resource_name}"] += 1
        return

    if not (
        post_urn.startswith("urn:li:share:") or post_urn.startswith("urn:li:ugcPost:")
    ):
        return

    timestamp = activity.get("created", {}).get("time")
    actor = extract_actor(element, activity)
    author = (
        activity.get("author")
        or activity.get("firstPublishedActor", {}).get("member", "")
        or actor
    )

    is_repost = activity.get("ugcOrigin") == "RESHARE" or bool(
        activity.get("responseContext", {}).get("parent")
    )
    post_type = "repost" if is_repost else "original"

    share_content = activity.get("specificContent", {}).get(
        "com.linkedin.ugc.ShareContent", {}
    )
    content = share_content.get("shareCommentary", {}).get("text", "")
    original_post_urn = None

    if is_repost:
        original_post_urn = activity.get("responseContext", {}).get(
            "parent"
        ) or activity.get("responseContext", {}).get("root")

    post_props = {
        "type": post_type,
        "has_content": bool(content),
        "timestamp": timestamp,
        "created_at": format_timestamp(timestamp),
    }
    if content:
        post_props["content"] = content[:200]
        # Extract URLs from full content before truncation
        urls = extract_urls_from_text(content)
        if urls:
            post_props["extracted_urls"] = urls
    if original_post_urn:
        post_props["original_post_urn"] = original_post_urn

    create_post_node(post_urn, posts, post_props)
    create_person_node(author, people)

    if original_post_urn:
        create_post_node(original_post_urn, posts)
        relationships.append(
            {
                "type": "REPOSTS",
                "from": post_urn,
                "to": original_post_urn,
                "properties": {
                    "relationship_type": "repost_of",
                    "timestamp": timestamp,
                },
            }
        )

    relationship_type = "REPOSTS" if is_repost else "CREATES"
    relationships.append(
        {
            "type": relationship_type,
            "from": author,
            "to": post_urn,
            "properties": {
                "timestamp": timestamp,
                "created_at": format_timestamp(timestamp),
            },
        }
    )


def process_comment(
    element, activity, people, posts, comments, relationships, skipped_by_reason
):
    """Process a comment element and update entities/relationships."""
    resource_name = element.get("resourceName", "")
    comment_id = activity.get("id", "")
    post_urn = activity.get("object", "")
    actor = extract_actor(element, activity)

    if not comment_id:
        skipped_by_reason[f"comment_no_id_{resource_name}"] += 1
        return
    if not post_urn:
        skipped_by_reason[f"comment_no_post_urn_{resource_name}"] += 1
        return
    if not actor:
        skipped_by_reason[f"comment_no_actor_{resource_name}"] += 1
        return

    timestamp = activity.get("created", {}).get("time")
    comment_text = activity.get("message", {}).get("text", "")

    # Build correct comment URN format: urn:li:comment:(parent_type:parent_id,comment_id)
    comment_urn = build_comment_urn(post_urn, comment_id)
    if not comment_urn:
        skipped_by_reason[f"comment_invalid_urn_{resource_name}"] += 1
        return

    response_context = activity.get("responseContext", {})
    parent_comment_urn = _extract_parent_comment_urn(
        activity, response_context, post_urn
    )

    # Generate URL from parent post URN
    comment_url = comment_urn_to_post_url(comment_urn) or ""

    if comment_urn not in comments:
        comment_props = {
            "urn": comment_urn,
            "comment_id": comment_id,
            "text": comment_text[:200] if comment_text else "",
            "timestamp": timestamp,
            "created_at": format_timestamp(timestamp),
            "url": comment_url,
        }
        # Extract URLs from full comment text before truncation
        if comment_text:
            urls = extract_urls_from_text(comment_text)
            if urls:
                comment_props["extracted_urls"] = urls

        comments[comment_urn] = {
            "id": comment_urn,
            "label": "Comment",
            "properties": comment_props,
        }

    create_post_node(post_urn, posts)
    create_person_node(actor, people)

    if parent_comment_urn and parent_comment_urn not in comments:
        parsed = parse_comment_urn(parent_comment_urn)
        parent_comment_id = parsed.get("comment_id") if parsed else None
        parent_comment_url = comment_urn_to_post_url(parent_comment_urn) or ""
        comments[parent_comment_urn] = {
            "id": parent_comment_urn,
            "label": "Comment",
            "properties": {
                "urn": parent_comment_urn,
                "comment_id": parent_comment_id or "",
                "text": "",
                "url": parent_comment_url,
            },
        }

    relationships.append(
        {
            "type": "CREATES",
            "from": actor,
            "to": comment_urn,
            "properties": {
                "timestamp": timestamp,
                "created_at": format_timestamp(timestamp),
            },
        }
    )

    target_urn = parent_comment_urn if parent_comment_urn else post_urn
    relationships.append(
        {
            "type": "COMMENTS_ON",
            "from": comment_urn,
            "to": target_urn,
            "properties": {
                "timestamp": timestamp,
                "created_at": format_timestamp(timestamp),
            },
        }
    )


def process_instant_repost(
    element, activity, people, posts, relationships, skipped_by_reason
):
    """Process an instant repost element and update entities/relationships."""
    resource_name = element.get("resourceName", "")
    reposted_share = activity.get("repostedContent", {}).get("share", "")
    actor = extract_actor(element, activity)

    if not reposted_share:
        skipped_by_reason[f"instant_repost_no_share_{resource_name}"] += 1
        return
    if not actor:
        skipped_by_reason[f"instant_repost_no_author_{resource_name}"] += 1
        return

    timestamp = activity.get("created", {}).get("time")

    create_post_node(reposted_share, posts)
    create_person_node(actor, people)

    relationships.append(
        {
            "type": "REPOSTS",
            "from": actor,
            "to": reposted_share,
            "properties": {
                "timestamp": timestamp,
                "created_at": format_timestamp(timestamp),
                "repost_type": "instant",
            },
        }
    )


def extract_entities_and_relationships(elements):
    """
    Extract entities (Posts, People, Comments, Reactions) and relationships.

    Returns:
        dict with 'nodes' and 'relationships' lists for Neo4j import
    """
    people = {}
    posts = {}
    comments = {}
    relationships = []
    skipped_by_reason = defaultdict(int)

    resource_counts, method_counts, resource_examples = summarize_resources(elements)

    print(f"\n🔍 Processing {len(elements)} elements...")

    for element in elements:
        resource_name = element.get("resourceName", "")
        activity = element.get("activity", {})

        if RESOURCE_REACTIONS in resource_name:
            process_reaction(
                element, activity, people, posts, relationships, skipped_by_reason
            )
        elif RESOURCE_POST in resource_name.lower() or RESOURCE_POSTS in resource_name:
            process_post(
                element, activity, people, posts, relationships, skipped_by_reason
            )
        elif RESOURCE_COMMENTS in resource_name:
            process_comment(
                element,
                activity,
                people,
                posts,
                comments,
                relationships,
                skipped_by_reason,
            )
        elif RESOURCE_INSTANT_REPOSTS in resource_name:
            process_instant_repost(
                element, activity, people, posts, relationships, skipped_by_reason
            )

    nodes = []
    nodes.extend(people.values())
    nodes.extend(posts.values())
    nodes.extend(comments.values())

    print(f"\n📊 Processing summary:")
    print_resource_summary(resource_counts, method_counts, resource_examples, top_n=10)
    if skipped_by_reason:
        print(f"   Skipped elements:")
        for reason, count in sorted(skipped_by_reason.items()):
            print(f"     • {reason}: {count}")
    print(f"\n📦 Extracted entities:")
    print(f"   People: {len(people)}")
    print(f"   Posts: {len(posts)}")
    print(f"   Comments: {len(comments)}")
    print(f"   Relationships: {len(relationships)}")

    return {
        "nodes": nodes,
        "relationships": relationships,
        "statistics": {
            "people": len(people),
            "posts": len(posts),
            "comments": len(comments),
            "relationships": len(relationships),
        },
    }


def print_summary(data):
    """Print summary of extracted data."""
    stats = data["statistics"]

    print("\n" + "=" * 60)
    print("📊 NEO4J DATA EXTRACTION SUMMARY")
    print("=" * 60)

    print(f"\n📦 ENTITIES:")
    print(f"   People: {stats['people']}")
    print(f"   Posts: {stats['posts']}")
    print(f"   Comments: {stats['comments']}")

    print(f"\n🔗 RELATIONSHIPS:")
    print(f"   Total: {stats['relationships']}")

    rel_types = defaultdict(int)
    for rel in data["relationships"]:
        rel_types[rel["type"]] += 1

    print(f"   By type:")
    for rel_type, count in sorted(rel_types.items()):
        print(f"     • {rel_type}: {count}")

    print("\n" + "=" * 60)


def save_neo4j_data(data, filename="neo4j_data.json"):
    """Save Neo4j-ready data to JSON file with timestamp to avoid overwriting."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name, ext = os.path.splitext(filename)
    filename = f"{base_name}_{timestamp}{ext}"
    filepath = OUTPUT_DIR / filename

    neo4j_format = {
        "nodes": [
            {
                "id": node["id"],
                "labels": [node["label"]],
                "properties": node["properties"],
            }
            for node in data["nodes"]
        ],
        "relationships": [
            {
                "type": rel["type"],
                "startNode": rel["from"],
                "endNode": rel["to"],
                "properties": rel["properties"],
            }
            for rel in data["relationships"]
        ],
        "statistics": data["statistics"],
    }

    with open(filepath, "w") as f:
        json.dump(neo4j_format, f, indent=2)

    print(f"💾 Neo4j data saved to {filepath}")


def parse_start_time(value):
    """Parse a start time string into epoch milliseconds."""
    if not value:
        return None

    try:
        return int(value)
    except ValueError:
        pass

    try:
        parsed = datetime.fromisoformat(value)
        return int(parsed.timestamp() * 1000)
    except ValueError:
        pass

    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
        return int(parsed.timestamp() * 1000)
    except ValueError:
        return None


def get_all_post_activities(start_time=None):
    """Fetch all changelog data related to public posts."""
    post_related_resources = [
        RESOURCE_REACTIONS,
        RESOURCE_COMMENTS,
        RESOURCE_POSTS,
        RESOURCE_POST,
        RESOURCE_INSTANT_REPOSTS,
    ]

    print("🔍 Fetching all post-related activities...")
    elements = fetch_changelog_data(
        resource_filter=post_related_resources, start_time=start_time
    )
    print(f"✅ Total post-related elements: {len(elements)}")
    return elements


def main():
    """Main function to extract entities and relationships."""
    parser = argparse.ArgumentParser(
        description="Extract graph data and activity statistics."
    )
    parser.add_argument(
        "--start-date",
        dest="start_date",
        help="Start date/time (ISO 8601 or epoch ms) for extraction.",
    )
    args = parser.parse_args()

    start_time = parse_start_time(args.start_date)
    if args.start_date and start_time is None:
        print("❌ Invalid --start-date format. Use ISO 8601 or epoch milliseconds.")
        return

    print("🚀 LinkedIn Neo4j Data Extraction")
    print("=" * 60)

    elements = get_all_post_activities(start_time=start_time)

    if not elements:
        print("❌ No post-related data found")
        return

    # Save last processed timestamp
    max_timestamp = get_max_processed_at(elements)
    if max_timestamp:
        save_last_processed_timestamp(max_timestamp)

    print("\n🔍 Extracting entities and relationships...")
    data = extract_entities_and_relationships(elements)

    print_summary(data)
    save_neo4j_data(data)

    print("\n🔍 Analyzing activity statistics...")
    stats = extract_statistics(elements)
    print_statistics(stats)
    save_statistics(stats)

    print("\n✅ Extraction complete!")
    print("💡 Use the JSON file to import into Neo4j")


if __name__ == "__main__":
    main()
