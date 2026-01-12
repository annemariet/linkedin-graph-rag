#!/usr/bin/env python3
"""
Extract and analyze all LinkedIn activity history from Member Data Portability API.

Extracts statistics for:
- DMs (messages sent/received)
- Invites (sent/received)
- Reactions (by type)
- Posts (original, repost, repost with comment)
- Comments
"""

import json
import os
from collections import Counter
from datetime import datetime
from linkedin_api.utils.changelog import fetch_changelog_data
from linkedin_api.utils.summaries import print_resource_summary, summarize_resources


def get_all_changelog_data():
    """Fetch all changelog data by paginating through all results."""
    return fetch_changelog_data()


def extract_statistics(elements):
    """Extract statistics from changelog elements and track data quality."""

    resource_types, method_types, resource_examples = summarize_resources(elements)

    stats = {
        "messages": {"sent": 0, "received": 0, "total": 0},
        "invites": {"sent": 0, "received": 0, "total": 0},
        "reactions": Counter(),
        "posts": {"original": 0, "repost": 0, "repost_with_comment": 0, "total": 0},
        "comments": {"total": 0},
        "resource_types": resource_types,
        "method_types": method_types,
        "resource_examples": resource_examples,
        "data_quality": {
            "total_elements": len(elements),
            "importable": 0,
            "skipped": 0,
            "skipped_by_reason": Counter(),
            "reactions_importable": 0,
            "reactions_incomplete": 0,
            "comments_importable": 0,
            "comments_incomplete": 0,
        },
    }

    # Track skipped elements for investigation
    skipped_elements = []

    # Track actor to determine if action is by user
    user_actor = None

    for element in elements:
        resource_name = element.get("resourceName", "")
        actor = element.get("actor", "")
        activity = element.get("activity", {})
        is_importable = True
        skip_reason = None

        # Set user actor from first element (assuming consistent actor)
        if not user_actor and actor:
            user_actor = actor

        # Messages (DMs)
        if "messages" in resource_name.lower():
            stats["messages"]["total"] += 1
            if actor == user_actor:
                stats["messages"]["sent"] += 1
            else:
                stats["messages"]["received"] += 1

        # Invitations
        elif "invitation" in resource_name.lower():
            stats["invites"]["total"] += 1
            if actor == user_actor:
                stats["invites"]["sent"] += 1
            else:
                stats["invites"]["received"] += 1

        # Reactions - validate for Neo4j import
        elif (
            "socialActions/likes" in resource_name
            or "reaction" in resource_name.lower()
        ):
            reaction_type = activity.get("reactionType", "UNKNOWN")
            stats["reactions"][reaction_type] += 1

            # Check if reaction has required fields for import
            post_urn = activity.get("root") or activity.get("object", "")
            reaction_actor = activity.get("actor", "") or actor

            if not post_urn:
                is_importable = False
                skip_reason = "reaction_no_post_urn"
                stats["data_quality"]["reactions_incomplete"] += 1
            elif not reaction_actor:
                is_importable = False
                skip_reason = "reaction_no_actor"
                stats["data_quality"]["reactions_incomplete"] += 1
            else:
                stats["data_quality"]["reactions_importable"] += 1

        # Posts (UGC Posts)
        elif "ugcPost" in resource_name.lower() or "ugcPosts" in resource_name:
            stats["posts"]["total"] += 1

            # Determine post type from activity
            # Check if it's a repost (shares another post)
            if activity.get("resharedPost") or activity.get("resharedActivity"):
                # Check if there's a comment/commentary
                if activity.get("commentary") or activity.get("text"):
                    stats["posts"]["repost_with_comment"] += 1
                else:
                    stats["posts"]["repost"] += 1
            else:
                stats["posts"]["original"] += 1

        # Comments - validate for Neo4j import
        elif "comment" in resource_name.lower() or "comments" in resource_name.lower():
            stats["comments"]["total"] += 1

            # Check if comment has required fields
            comment_id = activity.get("id", "")
            post_urn = activity.get("object", "")
            comment_actor = activity.get("actor", "") or actor

            if not comment_id:
                is_importable = False
                skip_reason = "comment_no_id"
                stats["data_quality"]["comments_incomplete"] += 1
            elif not post_urn:
                is_importable = False
                skip_reason = "comment_no_post_urn"
                stats["data_quality"]["comments_incomplete"] += 1
            elif not comment_actor:
                is_importable = False
                skip_reason = "comment_no_actor"
                stats["data_quality"]["comments_incomplete"] += 1
            else:
                stats["data_quality"]["comments_importable"] += 1

        # Track skipped elements
        if not is_importable:
            stats["data_quality"]["skipped"] += 1
            stats["data_quality"]["skipped_by_reason"][skip_reason] += 1
            skipped_elements.append(
                {
                    "reason": skip_reason,
                    "resource_name": resource_name,
                    "element": element,
                }
            )
        else:
            stats["data_quality"]["importable"] += 1

    stats["skipped_elements"] = skipped_elements

    return stats


def print_statistics(stats):
    """Print formatted statistics."""

    print("\n" + "=" * 60)
    print("📊 LINKEDIN ACTIVITY STATISTICS")
    print("=" * 60)

    # Messages
    print(f"\n💬 MESSAGES (DMs):")
    print(f"   Total: {stats['messages']['total']}")
    print(f"   Sent: {stats['messages']['sent']}")
    print(f"   Received: {stats['messages']['received']}")

    # Invites
    print(f"\n👋 INVITATIONS:")
    print(f"   Total: {stats['invites']['total']}")
    print(f"   Sent: {stats['invites']['sent']}")
    print(f"   Received: {stats['invites']['received']}")

    # Reactions
    print(f"\n❤️  REACTIONS:")
    total_reactions = sum(stats["reactions"].values())
    print(f"   Total: {total_reactions}")
    print(f"   Importable to graph: {stats['data_quality']['reactions_importable']}")
    print(f"   Incomplete (skipped): {stats['data_quality']['reactions_incomplete']}")
    print(f"   By type:")
    for reaction_type, count in stats["reactions"].most_common():
        print(f"     • {reaction_type}: {count}")

    # Posts
    print(f"\n📝 POSTS:")
    print(f"   Total: {stats['posts']['total']}")
    print(f"   Original: {stats['posts']['original']}")
    print(f"   Reposts: {stats['posts']['repost']}")
    print(f"   Reposts with comment: {stats['posts']['repost_with_comment']}")

    # Comments
    print(f"\n💬 COMMENTS:")
    print(f"   Total: {stats['comments']['total']}")
    print(f"   Importable to graph: {stats['data_quality']['comments_importable']}")
    print(f"   Incomplete (skipped): {stats['data_quality']['comments_incomplete']}")

    # Data Quality Summary
    dq = stats["data_quality"]
    print(f"\n📦 DATA QUALITY SUMMARY:")
    print(f"   Total elements: {dq['total_elements']}")
    print(
        f"   Importable to graph: {dq['importable']} ({dq['importable']/dq['total_elements']*100:.1f}%)"
    )
    print(
        f"   Skipped (incomplete): {dq['skipped']} ({dq['skipped']/dq['total_elements']*100:.1f}%)"
    )

    if dq["skipped_by_reason"]:
        print(f"   Skipped by reason:")
        for reason, count in sorted(
            dq["skipped_by_reason"].items(), key=lambda x: -x[1]
        ):
            print(f"     • {reason}: {count}")

    print_resource_summary(
        stats["resource_types"],
        stats["method_types"],
        stats["resource_examples"],
        top_n=10,
    )

    print("\n" + "=" * 60)


def save_statistics(stats, filename="linkedin_statistics.json"):
    """Save statistics to JSON file with timestamp to avoid overwriting."""
    # Add timestamp to filename to avoid overwriting existing data
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name, ext = os.path.splitext(filename)
    filename = f"{base_name}_{timestamp}{ext}"

    # Convert Counter objects to dicts for JSON serialization
    stats_json = {
        "messages": stats["messages"],
        "invites": stats["invites"],
        "reactions": dict(stats["reactions"]),
        "posts": stats["posts"],
        "comments": stats["comments"],
        "resource_types": dict(stats["resource_types"]),
        "method_types": dict(stats["method_types"]),
        "resource_examples": stats["resource_examples"],
        "data_quality": {
            "total_elements": stats["data_quality"]["total_elements"],
            "importable": stats["data_quality"]["importable"],
            "skipped": stats["data_quality"]["skipped"],
            "skipped_by_reason": dict(stats["data_quality"]["skipped_by_reason"]),
            "reactions_importable": stats["data_quality"]["reactions_importable"],
            "reactions_incomplete": stats["data_quality"]["reactions_incomplete"],
            "comments_importable": stats["data_quality"]["comments_importable"],
            "comments_incomplete": stats["data_quality"]["comments_incomplete"],
        },
    }

    with open(filename, "w") as f:
        json.dump(stats_json, f, indent=2, default=str)

    print(f"💾 Statistics saved to {filename}")

    # Save skipped elements to separate file for investigation
    if stats.get("skipped_elements"):
        skipped_filename = filename.replace(".json", "_skipped.json")
        with open(skipped_filename, "w") as f:
            json.dump(stats["skipped_elements"], f, indent=2, default=str)
        print(
            f"💾 Skipped elements saved to {skipped_filename} ({len(stats['skipped_elements'])} elements)"
        )


def main():
    """Main function to extract and analyze LinkedIn data."""
    print("🚀 LinkedIn Data Extraction & Statistics")
    print("=" * 60)

    # Get all changelog data
    elements = get_all_changelog_data()

    if not elements:
        print("❌ No data retrieved")
        return

    # Extract statistics
    print("\n🔍 Analyzing data...")
    stats = extract_statistics(elements)

    # Print statistics
    print_statistics(stats)

    # Save to file
    save_statistics(stats)

    print("\n✅ Analysis complete!")


if __name__ == "__main__":
    main()
