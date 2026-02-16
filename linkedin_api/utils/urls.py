"""
URL extraction utilities.

Helpers for extracting URLs from posts and comments, including first-comment
URLs when the post author adds a link in their first comment.
"""

from __future__ import annotations

from linkedin_api.extract_resources import extract_urls_from_text


def get_urls_from_post_and_first_comment(
    nodes_by_id: dict[str, dict],
    relationships: list[dict],
    post_urn: str,
) -> list[str]:
    """
    Get URLs from post content and from the first comment if authored by post author.

    Many posts put the link in a first comment by the author. When the first
    top-level comment on a post is by the same person who created the post,
    extract URLs from that comment and merge with URLs from the post.

    Args:
        nodes_by_id: Dict mapping node id -> node (with properties)
        relationships: List of {type, from, to, properties}
        post_urn: The post URN to look up

    Returns:
        List of unique URLs from post content and optionally first author comment
    """
    urls = []
    post_node = nodes_by_id.get(post_urn, {})
    post_props = post_node.get("properties", {})
    content = post_props.get("content", "")
    urls.extend(post_props.get("extracted_urls", []) or extract_urls_from_text(content))

    post_author = _get_post_author(post_urn, relationships)
    if not post_author:
        return list(dict.fromkeys(urls))

    first_comment_urn = _get_first_comment_urn_on_post(
        post_urn, nodes_by_id, relationships
    )
    if not first_comment_urn:
        return list(dict.fromkeys(urls))

    first_comment_author = _get_comment_author(first_comment_urn, relationships)
    if first_comment_author != post_author:
        return list(dict.fromkeys(urls))

    first_comment_node = nodes_by_id.get(first_comment_urn, {})
    comment_props = first_comment_node.get("properties", {})
    comment_text = comment_props.get("text", "")
    if comment_text:
        comment_urls = comment_props.get(
            "extracted_urls", []
        ) or extract_urls_from_text(comment_text)
        urls.extend(comment_urls)

    return list(dict.fromkeys(urls))


def _get_post_author(post_urn: str, relationships: list[dict]) -> str | None:
    """Return Person URN who created the post, or None."""
    for r in relationships:
        if r.get("type") != "CREATES" or r.get("to") != post_urn:
            continue
        from_urn = r.get("from")
        if from_urn and from_urn.startswith("urn:li:person:"):
            return from_urn
    for r in relationships:
        if r.get("type") != "REPOSTS" or r.get("to") != post_urn:
            continue
        from_urn = r.get("from")
        if from_urn and from_urn.startswith("urn:li:person:"):
            return from_urn
    return None


def _get_comment_author(comment_urn: str, relationships: list[dict]) -> str | None:
    """Return Person URN who created the comment, or None."""
    for r in relationships:
        if r.get("type") != "CREATES" or r.get("to") != comment_urn:
            continue
        from_urn = r.get("from")
        if from_urn and from_urn.startswith("urn:li:person:"):
            return from_urn
    return None


def _get_first_comment_urn_on_post(
    post_urn: str,
    nodes_by_id: dict[str, dict],
    relationships: list[dict],
) -> str | None:
    """Return the URN of the first (by timestamp) top-level comment on the post."""
    top_level = []
    for r in relationships:
        if r.get("type") != "COMMENTS_ON" or r.get("to") != post_urn:
            continue
        comment_urn = r.get("from")
        if not comment_urn or not comment_urn.startswith("urn:li:comment:"):
            continue
        comment_node = nodes_by_id.get(comment_urn, {})
        if "Comment" not in comment_node.get("labels", []):
            continue
        ts = comment_node.get("properties", {}).get("timestamp") or 0
        top_level.append((ts, comment_urn))

    if not top_level:
        return None
    top_level.sort(key=lambda x: x[0])
    return top_level[0][1]
