"""
Per-element extraction preview for the review UI.

Runs existing process_* on a single changelog element with fresh dicts
and returns the delta (nodes + relationships) plus a trace of JSON paths used.
"""

from collections import defaultdict

from linkedin_api.extract_graph_data import (
    RESOURCE_COMMENTS,
    RESOURCE_INSTANT_REPOSTS,
    RESOURCE_POST,
    RESOURCE_POSTS,
    RESOURCE_REACTIONS,
    process_comment,
    process_instant_repost,
    process_post,
    process_reaction,
)


def extract_element_preview(element: dict) -> dict:
    """
    Extract graph entities and relationships for a single changelog element.

    Returns only the delta (nodes and relationships) produced by this element,
    plus a trace list of { json_path, value_used, field_name } for UI highlighting.

    Args:
        element: Raw changelog element dict (resourceName, activity, etc.).

    Returns:
        { "extracted": { "nodes": [...], "relationships": [...], "primary": ... }, "trace": [...] }
        primary is the main entity type for this element ("reaction", "post", "comment", "instant_repost").
    """
    people = {}
    posts = {}
    comments = {}
    relationships = []
    skipped_by_reason = defaultdict(int)
    trace = []

    resource_name = element.get("resourceName", "")
    activity = element.get("activity", {})

    if RESOURCE_REACTIONS in resource_name:
        process_reaction(
            element,
            activity,
            people,
            posts,
            relationships,
            skipped_by_reason,
            trace=trace,
        )
        primary = "reaction"
    elif RESOURCE_POST in resource_name.lower() or RESOURCE_POSTS in resource_name:
        process_post(
            element,
            activity,
            people,
            posts,
            relationships,
            skipped_by_reason,
            trace=trace,
        )
        primary = "post"
    elif RESOURCE_COMMENTS in resource_name:
        process_comment(
            element,
            activity,
            people,
            posts,
            comments,
            relationships,
            skipped_by_reason,
            trace=trace,
        )
        primary = "comment"
    elif RESOURCE_INSTANT_REPOSTS in resource_name:
        process_instant_repost(
            element,
            activity,
            people,
            posts,
            relationships,
            skipped_by_reason,
            trace=trace,
        )
        primary = "instant_repost"
    else:
        primary = "unknown"

    nodes = []
    nodes.extend(people.values())
    nodes.extend(posts.values())
    nodes.extend(comments.values())

    extracted = {
        "nodes": nodes,
        "relationships": relationships,
        "primary": primary,
        "resource_name": resource_name,
        "skipped_reasons": dict(skipped_by_reason),
    }
    return {"extracted": extracted, "trace": trace}
