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
