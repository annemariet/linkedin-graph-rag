"""
Utilities for extracting and analyzing LinkedIn changelog activity elements.

This module provides shared functions for:
- Extracting common fields from changelog elements
- Determining post types (original, repost, repost with comment)
- Extracting reaction types
- Detecting element types (reactions, posts, comments, messages, invitations)
- Converting timestamps
"""

from typing import Any, Dict, Optional, Union
from datetime import datetime, timezone


def extract_element_fields(element: Dict) -> Dict[str, Any]:
    """
    Extract common fields from a changelog element.

    Args:
        element: A changelog element dictionary

    Returns:
        Dictionary with extracted fields:
        - resource_name: The resource name
        - method_name: The method name
        - actor: The actor URN (from element or activity)
        - activity: The activity dictionary
        - timestamp: The timestamp in milliseconds (or None)
    """
    resource_name = element.get("resourceName", "")
    method_name = element.get("methodName", "")
    activity = element.get("activity", {})

    # Actor can be in element or activity
    actor = element.get("actor", "") or activity.get("actor", "")

    # Extract timestamp from activity.created.time
    timestamp = None
    if activity:
        created = activity.get("created", {})
        if isinstance(created, dict):
            timestamp = created.get("time")

    return {
        "resource_name": resource_name,
        "method_name": method_name,
        "actor": actor,
        "activity": activity,
        "timestamp": timestamp,
    }


def determine_post_type(activity: Dict) -> str:
    """
    Determine the type of a post from its activity data.

    Args:
        activity: The activity dictionary from a post element

    Returns:
        One of: 'original', 'repost', 'repost_with_comment'
    """
    # Check if it's a repost via ugcOrigin
    is_repost = activity.get("ugcOrigin") == "RESHARE"

    # Also check responseContext.parent which indicates original post
    if not is_repost:
        is_repost = bool(activity.get("responseContext", {}).get("parent"))

    # Check for resharedPost or resharedActivity
    if not is_repost:
        is_repost = bool(
            activity.get("resharedPost") or activity.get("resharedActivity")
        )

    if not is_repost:
        return "original"

    # Check if there's commentary/comment
    # Check shareCommentary text
    share_content = activity.get("specificContent", {}).get(
        "com.linkedin.ugc.ShareContent", {}
    )
    commentary = share_content.get("shareCommentary", {}).get("text", "")
    has_commentary = bool(commentary)

    # Also check for text field directly
    if not has_commentary:
        has_commentary = bool(activity.get("text") or activity.get("commentary"))

    if has_commentary:
        return "repost_with_comment"

    return "repost"


def extract_reaction_type(activity: Dict) -> str:
    """
    Extract the reaction type from an activity.

    Args:
        activity: The activity dictionary

    Returns:
        The reaction type (e.g., 'LIKE', 'CELEBRATE') or 'UNKNOWN'
    """
    return str(activity.get("reactionType", "UNKNOWN"))


def extract_timestamp(
    activity: Dict, as_iso: bool = False
) -> Optional[Union[int, str]]:
    """
    Extract timestamp from activity.

    Args:
        activity: The activity dictionary
        as_iso: If True, return ISO format string; otherwise return milliseconds

    Returns:
        Timestamp in milliseconds, ISO string, or None
    """
    created = activity.get("created", {})
    if not isinstance(created, dict):
        return None

    timestamp: Optional[int] = created.get("time")
    if timestamp is None:
        return None

    if as_iso:
        return datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )

    return timestamp


def is_reaction_element(element: Dict) -> bool:
    """
    Check if an element represents a reaction/like.

    Args:
        element: The changelog element

    Returns:
        True if the element is a reaction
    """
    resource_name = element.get("resourceName", "").lower()
    return "socialactions/likes" in resource_name or "reaction" in resource_name


def is_post_element(element: Dict) -> bool:
    """
    Check if an element represents a post.

    Args:
        element: The changelog element

    Returns:
        True if the element is a post
    """
    resource_name = element.get("resourceName", "").lower()
    return "ugcpost" in resource_name


def is_comment_element(element: Dict) -> bool:
    """
    Check if an element represents a comment.

    Args:
        element: The changelog element

    Returns:
        True if the element is a comment
    """
    resource_name = element.get("resourceName", "").lower()
    return "comment" in resource_name or "comments" in resource_name


def is_message_element(element: Dict) -> bool:
    """
    Check if an element represents a message (DM).

    Args:
        element: The changelog element

    Returns:
        True if the element is a message
    """
    resource_name = element.get("resourceName", "").lower()
    return "message" in resource_name or "messages" in resource_name


def is_invitation_element(element: Dict) -> bool:
    """
    Check if an element represents an invitation.

    Args:
        element: The changelog element

    Returns:
        True if the element is an invitation
    """
    resource_name = element.get("resourceName", "").lower()
    return "invitation" in resource_name or "invitations" in resource_name
