#!/usr/bin/env python3
"""
Extract entities and relationships from LinkedIn public post activities for Neo4j.

Focuses on:
- Posts (original, reposts)
- People (actors, authors)
- Comments
- Reactions

Relationships:
- Person REACTS_TO Post
- Person CREATED Comment
- Comment COMMENTED_ON Post (top-level comments)
- Comment COMMENTED_ON Comment (comment replies)
- Person REPOSTS Post
- Person CREATES Post
"""

import json
import os
from collections import defaultdict
from datetime import datetime
from linkedin_api.utils.changelog import fetch_changelog_data
from linkedin_api.utils.summaries import print_resource_summary, summarize_resources
from linkedin_api.utils.urns import extract_urn_id, urn_to_post_url


def get_all_post_activities():
    """Fetch all changelog data related to public posts."""
    post_related_resources = [
        "socialActions/likes",
        "socialActions/comments",
        "ugcPosts",
        "ugcPost",
        "instantReposts",
    ]

    print("🔍 Fetching all post-related activities...")
    elements = fetch_changelog_data(resource_filter=post_related_resources)
    print(f"✅ Total post-related elements: {len(elements)}")
    return elements


def extract_entities_and_relationships(elements):
    """
    Extract entities (Posts, People, Comments, Reactions) and relationships.

    Returns:
        dict with 'nodes' and 'relationships' lists for Neo4j import
    """

    # Track unique entities
    people = {}  # person_urn -> person_data
    posts = {}  # post_urn -> post_data
    comments = {}  # comment_urn -> comment_data

    # Track relationships
    relationships = []

    # Precompute resource stats for summary
    resource_counts, method_counts, resource_examples = summarize_resources(elements)
    skipped_by_reason = defaultdict(int)

    print(f"\n🔍 Processing {len(elements)} elements...")

    for element in elements:
        resource_name = element.get("resourceName", "")
        # Actor can be in element or activity
        actor = element.get("actor", "") or element.get("activity", {}).get("actor", "")
        activity = element.get("activity", {})
        timestamp = activity.get("created", {}).get("time")

        # Extract person (actor) - check both element and activity
        if actor and actor.startswith("urn:li:person:"):
            person_id = extract_urn_id(actor)
            if person_id and actor not in people:
                people[actor] = {
                    "id": actor,
                    "person_id": person_id,
                    "label": "Person",
                    "properties": {
                        "urn": actor,
                        "person_id": person_id,
                    },
                }

        # Reactions (socialActions/likes)
        if "socialActions/likes" in resource_name:
            # Reactions can point to 'root' or 'object' field, and may use 'activity' or 'ugcPost' URNs
            post_urn = activity.get("root") or activity.get("object", "")
            reaction_type = activity.get("reactionType", "UNKNOWN")
            # Actor is in activity for reactions
            reaction_actor = activity.get("actor", "") or actor

            if not post_urn:
                skipped_by_reason[f"reaction_no_post_urn_{resource_name}"] += 1
                continue
            if not reaction_actor:
                skipped_by_reason[f"reaction_no_actor_{resource_name}"] += 1
                continue

            actor = reaction_actor

            if post_urn and actor:
                # Normalize post URN - convert activity URNs to ugcPost if needed
                # LinkedIn uses both urn:li:activity: and urn:li:ugcPost: for posts
                normalized_post_urn = post_urn
                if post_urn.startswith("urn:li:activity:"):
                    # Try to convert activity to ugcPost format (may not always work)
                    # For now, keep as activity but track it
                    normalized_post_urn = post_urn

                # Track post
                if normalized_post_urn not in posts:
                    post_id = extract_urn_id(normalized_post_urn)
                    posts[normalized_post_urn] = {
                        "id": normalized_post_urn,
                        "label": "Post",
                        "properties": {
                            "urn": normalized_post_urn,
                            "post_id": post_id,
                            "url": urn_to_post_url(normalized_post_urn) or "",
                            "original_urn": post_urn,  # Keep original for reference
                        },
                    }

                # Track actor as person
                if actor and actor.startswith("urn:li:person:"):
                    person_id = extract_urn_id(actor)
                    if person_id and actor not in people:
                        people[actor] = {
                            "id": actor,
                            "person_id": person_id,
                            "label": "Person",
                            "properties": {
                                "urn": actor,
                                "person_id": person_id,
                            },
                        }

                # Create REACTS_TO relationship
                relationships.append(
                    {
                        "type": "REACTS_TO",
                        "from": actor,
                        "to": normalized_post_urn,
                        "properties": {
                            "reaction_type": reaction_type,
                            "timestamp": timestamp,
                            "created_at": (
                                datetime.fromtimestamp(timestamp / 1000).isoformat()
                                if timestamp
                                else None
                            ),
                        },
                    }
                )

        # Posts (ugcPosts) - posts are identified by 'id' field which can be 'urn:li:share:' or 'urn:li:ugcPost:'
        elif "ugcPost" in resource_name.lower():
            # Posts have 'id' field with URN like 'urn:li:share:...' or 'urn:li:ugcPost:...'
            post_urn = activity.get("id", "")

            if not post_urn:
                skipped_by_reason[f"post_no_id_{resource_name}"] += 1
                continue

            if post_urn and (
                post_urn.startswith("urn:li:share:")
                or post_urn.startswith("urn:li:ugcPost:")
            ):
                post_id = extract_urn_id(post_urn)
                author = (
                    activity.get("author")
                    or activity.get("firstPublishedActor", {}).get("member", "")
                    or actor
                )

                # Determine if it's a repost
                # Check ugcOrigin field: "RESHARE" means repost
                # Also check responseContext.parent which indicates original post
                is_repost = activity.get("ugcOrigin") == "RESHARE" or bool(
                    activity.get("responseContext", {}).get("parent")
                )
                post_type = "repost" if is_repost else "original"

                # Get post content text if present
                share_content = activity.get("specificContent", {}).get(
                    "com.linkedin.ugc.ShareContent", {}
                )
                content = share_content.get("shareCommentary", {}).get("text", "")
                has_content = bool(content)

                # Get original post URN if repost
                original_post_urn = None
                if is_repost:
                    original_post_urn = activity.get("responseContext", {}).get(
                        "parent"
                    ) or activity.get("responseContext", {}).get("root")

                # Track post
                if post_urn not in posts:
                    post_props = {
                        "urn": post_urn,
                        "post_id": post_id,
                        "url": urn_to_post_url(post_urn) or "",
                        "type": post_type,
                        "has_content": has_content,
                        "timestamp": timestamp,
                        "created_at": (
                            datetime.fromtimestamp(timestamp / 1000).isoformat()
                            if timestamp
                            else None
                        ),
                    }
                    if content:
                        post_props["content"] = content[:200]  # Truncate for storage
                    if original_post_urn:
                        post_props["original_post_urn"] = original_post_urn

                    posts[post_urn] = {
                        "id": post_urn,
                        "label": "Post",
                        "properties": post_props,
                    }

                # Track author
                if author and author.startswith("urn:li:person:"):
                    person_id = extract_urn_id(author)
                    if person_id and author not in people:
                        people[author] = {
                            "id": author,
                            "person_id": person_id,
                            "label": "Person",
                            "properties": {
                                "urn": author,
                                "person_id": person_id,
                            },
                        }

                    # Create CREATES or REPOSTS relationship
                    if is_repost:
                        relationships.append(
                            {
                                "type": "REPOSTS",
                                "from": author,
                                "to": post_urn,
                                "properties": {
                                    "timestamp": timestamp,
                                    "created_at": (
                                        datetime.fromtimestamp(
                                            timestamp / 1000
                                        ).isoformat()
                                        if timestamp
                                        else None
                                    ),
                                },
                            }
                        )
                        # Also link to original post if available
                        if original_post_urn:
                            # Track original post
                            if original_post_urn not in posts:
                                orig_post_id = extract_urn_id(original_post_urn)
                                posts[original_post_urn] = {
                                    "id": original_post_urn,
                                    "label": "Post",
                                    "properties": {
                                        "urn": original_post_urn,
                                        "post_id": orig_post_id,
                                        "url": urn_to_post_url(original_post_urn) or "",
                                    },
                                }
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
                    else:
                        relationships.append(
                            {
                                "type": "CREATES",
                                "from": author,
                                "to": post_urn,
                                "properties": {
                                    "timestamp": timestamp,
                                    "created_at": (
                                        datetime.fromtimestamp(
                                            timestamp / 1000
                                        ).isoformat()
                                        if timestamp
                                        else None
                                    ),
                                },
                            }
                        )

        # Comments (socialActions/comments)
        elif "socialActions/comments" in resource_name:
            # Comments have 'id' (numeric) and 'object' (post URN)
            comment_id = activity.get("id", "")
            post_urn = activity.get("object", "")  # This is the post being commented on
            # Actor is in activity for comments
            comment_actor = activity.get("actor", "") or actor

            if not comment_id:
                skipped_by_reason[f"comment_no_id_{resource_name}"] += 1
                continue
            if not post_urn:
                skipped_by_reason[f"comment_no_post_urn_{resource_name}"] += 1
                continue
            if not comment_actor:
                skipped_by_reason[f"comment_no_actor_{resource_name}"] += 1
                continue

            actor = comment_actor

            # Create comment URN from ID if needed
            comment_urn = f"urn:li:comment:{comment_id}"

            if comment_urn and post_urn and actor:
                # Get comment text
                comment_text = activity.get("message", {}).get("text", "")

                # Check if this is a reply to another comment
                # LinkedIn may use responseContext.parent for comment replies
                parent_comment_urn = None
                response_context = activity.get("responseContext", {})
                parent_urn = response_context.get("parent") or response_context.get(
                    "root"
                )

                # If parent is a comment URN, this is a reply
                if parent_urn and parent_urn.startswith("urn:li:comment:"):
                    parent_comment_urn = parent_urn
                # If parent is the post, this is a top-level comment (already have post_urn)

                # Track comment
                if comment_urn not in comments:
                    comments[comment_urn] = {
                        "id": comment_urn,
                        "label": "Comment",
                        "properties": {
                            "urn": comment_urn,
                            "comment_id": comment_id,
                            "text": (
                                comment_text[:200] if comment_text else ""
                            ),  # Truncate
                            "timestamp": timestamp,
                            "created_at": (
                                datetime.fromtimestamp(timestamp / 1000).isoformat()
                                if timestamp
                                else None
                            ),
                        },
                    }

                # Track post (can be ugcPost or activity URN)
                if post_urn not in posts:
                    post_id = extract_urn_id(post_urn)
                    posts[post_urn] = {
                        "id": post_urn,
                        "label": "Post",
                        "properties": {
                            "urn": post_urn,
                            "post_id": post_id,
                            "url": urn_to_post_url(post_urn) or "",
                        },
                    }

                # Track commenter
                if actor and actor.startswith("urn:li:person:"):
                    person_id = extract_urn_id(actor)
                    if person_id and actor not in people:
                        people[actor] = {
                            "id": actor,
                            "person_id": person_id,
                            "label": "Person",
                            "properties": {
                                "urn": actor,
                                "person_id": person_id,
                            },
                        }

                    # Create Person CREATED Comment relationship
                    relationships.append(
                        {
                            "type": "CREATED",
                            "from": actor,
                            "to": comment_urn,
                            "properties": {
                                "timestamp": timestamp,
                                "created_at": (
                                    datetime.fromtimestamp(timestamp / 1000).isoformat()
                                    if timestamp
                                    else None
                                ),
                            },
                        }
                    )

                # Create Comment COMMENTED_ON relationship
                # If parent_comment_urn exists, comment is replying to another comment
                # Otherwise, comment is on the post
                target_urn = parent_comment_urn if parent_comment_urn else post_urn

                # Ensure parent comment exists if this is a reply
                if parent_comment_urn and parent_comment_urn not in comments:
                    # Create a minimal parent comment node if we haven't seen it yet
                    parent_comment_id = extract_urn_id(parent_comment_urn)
                    comments[parent_comment_urn] = {
                        "id": parent_comment_urn,
                        "label": "Comment",
                        "properties": {
                            "urn": parent_comment_urn,
                            "comment_id": parent_comment_id or "",
                            "text": "",  # Will be filled if we process the parent later
                        },
                    }

                relationships.append(
                    {
                        "type": "COMMENTED_ON",
                        "from": comment_urn,
                        "to": target_urn,
                        "properties": {
                            "timestamp": timestamp,
                            "created_at": (
                                datetime.fromtimestamp(timestamp / 1000).isoformat()
                                if timestamp
                                else None
                            ),
                        },
                    }
                )

        # Instant Reposts
        elif "instantReposts" in resource_name:
            # Instant reposts have repostedContent.share pointing to the post
            reposted_share = activity.get("repostedContent", {}).get("share", "")
            author = actor

            if not reposted_share:
                skipped_by_reason[f"instant_repost_no_share_{resource_name}"] += 1
                continue
            if not author:
                skipped_by_reason[f"instant_repost_no_author_{resource_name}"] += 1
                continue

            if reposted_share and author:
                # Track the reposted post
                if reposted_share not in posts:
                    post_id = extract_urn_id(reposted_share)
                    posts[reposted_share] = {
                        "id": reposted_share,
                        "label": "Post",
                        "properties": {
                            "urn": reposted_share,
                            "post_id": post_id,
                            "url": urn_to_post_url(reposted_share) or "",
                        },
                    }

                # Track author
                if author and author.startswith("urn:li:person:"):
                    person_id = extract_urn_id(author)
                    if person_id and author not in people:
                        people[author] = {
                            "id": author,
                            "person_id": person_id,
                            "label": "Person",
                            "properties": {
                                "urn": author,
                                "person_id": person_id,
                            },
                        }

                    # Create REPOSTS relationship
                    relationships.append(
                        {
                            "type": "REPOSTS",
                            "from": author,
                            "to": reposted_share,
                            "properties": {
                                "timestamp": timestamp,
                                "created_at": (
                                    datetime.fromtimestamp(timestamp / 1000).isoformat()
                                    if timestamp
                                    else None
                                ),
                                "repost_type": "instant",
                            },
                        }
                    )

    # Convert entities to nodes format
    nodes = []
    nodes.extend(people.values())
    nodes.extend(posts.values())
    nodes.extend(comments.values())

    # Debug output
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

    # Count relationship types
    rel_types = defaultdict(int)
    for rel in data["relationships"]:
        rel_types[rel["type"]] += 1

    print(f"   By type:")
    for rel_type, count in sorted(rel_types.items()):
        print(f"     • {rel_type}: {count}")

    print("\n" + "=" * 60)


def save_neo4j_data(data, filename="neo4j_data.json"):
    """Save Neo4j-ready data to JSON file with timestamp to avoid overwriting."""
    # Add timestamp to filename to avoid overwriting existing data
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name, ext = os.path.splitext(filename)
    filename = f"{base_name}_{timestamp}{ext}"

    # Format for Neo4j import
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

    with open(filename, "w") as f:
        json.dump(neo4j_format, f, indent=2)

    print(f"💾 Neo4j data saved to {filename}")


def main():
    """Main function to extract entities and relationships."""
    print("🚀 LinkedIn Neo4j Data Extraction")
    print("=" * 60)

    # Get all post-related activities
    elements = get_all_post_activities()

    if not elements:
        print("❌ No post-related data found")
        return

    # Extract entities and relationships
    print("\n🔍 Extracting entities and relationships...")
    data = extract_entities_and_relationships(elements)

    # Print summary
    print_summary(data)

    # Save to file
    save_neo4j_data(data)

    print("\n✅ Extraction complete!")
    print("💡 Use the JSON file to import into Neo4j")


if __name__ == "__main__":
    main()
