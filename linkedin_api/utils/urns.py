"""
Utilities for converting LinkedIn URNs to HTML URLs.

LinkedIn uses URN (Uniform Resource Name) syntax in their API responses,
which need to be converted to standard URLs for accessing HTML pages.
"""

from typing import Optional


def extract_urn_id(urn: str) -> Optional[str]:
    """
    Extract the ID portion from a LinkedIn URN.

    Examples:
        urn:li:person:k_ho7OlN0r -> k_ho7OlN0r
        urn:li:ugcPost:7398404729531285504 -> 7398404729531285504

    Args:
        urn: The LinkedIn URN string

    Returns:
        The ID portion of the URN, or None if invalid
    """
    if not urn or not isinstance(urn, str):
        return None

    if ":" not in urn:
        return urn

    parts = urn.split(":")
    if len(parts) < 4:
        return None

    return parts[-1]


def parse_comment_urn(comment_urn: str) -> Optional[dict]:
    """
    Parse a LinkedIn comment URN to extract parent post info and comment ID.

    Comment URNs have the format:
    urn:li:comment:(<parent_type>:<parent_id>,<comment_id>)

    Examples:
        urn:li:comment:(activity:7401982773730856960,7402008011394912257)
        urn:li:comment:(ugcPost:7415421701938683905,7415508043578454016)

    Args:
        comment_urn: The comment URN string

    Returns:
        Dict with 'parent_type', 'parent_id', 'comment_id', and 'parent_urn', or None if invalid
    """
    if not comment_urn or not isinstance(comment_urn, str):
        return None

    if not comment_urn.startswith("urn:li:comment:"):
        return None

    # Extract the part after "urn:li:comment:"
    comment_part = comment_urn[len("urn:li:comment:") :]

    # Check if it's the simple format (just comment_id) - old format
    if not comment_part.startswith("("):
        return {
            "parent_type": None,
            "parent_id": None,
            "comment_id": comment_part,
            "parent_urn": None,
        }

    # Parse the complex format: (parent_type:parent_id,comment_id)
    if not comment_part.startswith("(") or not comment_part.endswith(")"):
        return None

    inner = comment_part[1:-1]  # Remove parentheses
    parts = inner.split(",")
    if len(parts) != 2:
        return None

    parent_part = parts[0].strip()
    comment_id = parts[1].strip()

    # Parse parent_type:parent_id
    if ":" not in parent_part:
        return None

    parent_type, parent_id = parent_part.split(":", 1)
    parent_urn = f"urn:li:{parent_type}:{parent_id}"

    return {
        "parent_type": parent_type,
        "parent_id": parent_id,
        "comment_id": comment_id,
        "parent_urn": parent_urn,
    }


def extract_parent_post_urn_from_comment(comment_urn: str) -> Optional[str]:
    """
    Extract the parent post URN from a comment URN.

    Args:
        comment_urn: The comment URN

    Returns:
        The parent post URN, or None if invalid or not found
    """
    parsed = parse_comment_urn(comment_urn)
    if not parsed or not parsed["parent_urn"]:
        return None

    parent_urn = parsed["parent_urn"]
    # Only return if it's a post-like URN (activity, ugcPost, share)
    if any(
        parent_urn.startswith(f"urn:li:{pt}:")
        for pt in ["activity", "ugcPost", "share", "groupPost"]
    ):
        return parent_urn

    return None


def comment_urn_to_post_url(comment_urn: str) -> Optional[str]:
    """
    Convert a comment URN to the URL of its parent post.

    Comments don't have direct URLs - they link to their parent post.

    Args:
        comment_urn: The comment URN

    Returns:
        The parent post URL, or None if invalid
    """
    parent_urn = extract_parent_post_urn_from_comment(comment_urn)
    if not parent_urn:
        return None

    return urn_to_post_url(parent_urn)


def build_comment_urn(parent_urn: str, comment_id: str) -> Optional[str]:
    """
    Build a comment URN from parent post URN and comment ID.

    Args:
        parent_urn: The parent post URN (e.g., "urn:li:activity:123")
        comment_id: The comment ID

    Returns:
        The comment URN, or None if invalid
    """
    if not parent_urn or not comment_id:
        return None

    if not parent_urn.startswith("urn:li:"):
        return None

    # Extract parent type and ID from parent_urn
    # Format: urn:li:<type>:<id>
    parts = parent_urn.split(":", 3)
    if len(parts) < 4:
        return None

    parent_type = parts[2]  # e.g., "activity", "ugcPost"
    parent_id = parts[3]  # The ID

    return f"urn:li:comment:({parent_type}:{parent_id},{comment_id})"


def urn_to_post_url(urn: str) -> Optional[str]:
    """
    Convert a LinkedIn post URN to a public HTML URL.

    LinkedIn post URLs use the format:
    https://www.linkedin.com/feed/update/{urn}

    Args:
        urn: The post URN (e.g., "urn:li:ugcPost:...", "urn:li:share:...", "urn:li:activity:...")

    Returns:
        The public LinkedIn post URL, or None if invalid
    """
    if not urn or not urn.startswith("urn:li:"):
        return None

    return f"https://www.linkedin.com/feed/update/{urn}"
