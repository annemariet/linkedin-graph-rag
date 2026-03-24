"""
Extract post creation timestamp from LinkedIn URN using Snowflake ID encoding.

LinkedIn post/activity IDs encode the creation timestamp in the first 41 bits
(Snowflake-style). See Ollie-Boyd/Linkedin-post-timestamp-extractor.
"""

from typing import Optional

from linkedin_api.content_store import _ms_to_iso
from linkedin_api.utils.urns import extract_urn_id


def timestamp_ms_from_linkedin_id(linkedin_id: str | int) -> Optional[int]:
    """
    Extract Unix timestamp (ms) from a LinkedIn post/activity ID.

    Works for urn:li:ugcPost:ID, urn:li:activity:ID, urn:li:share:ID.
    Returns None for comment URNs or invalid IDs.

    Args:
        linkedin_id: Numeric ID string or int (e.g. "7398404729531285504")

    Returns:
        Timestamp in milliseconds since epoch, or None if not extractable
    """
    try:
        if isinstance(linkedin_id, str):
            n = int(linkedin_id)
        else:
            n = int(linkedin_id)
    except (ValueError, TypeError):
        return None

    if n <= 0:
        return None

    binary = bin(n)[2:]
    if len(binary) < 41:
        return None

    first_41 = binary[:41]
    ts_ms = int(first_41, 2)
    # Sanity: must be between 2005 and 2030
    if ts_ms < 1100000000000 or ts_ms > 1900000000000:
        return None
    return ts_ms


def post_created_at_from_urn(urn: str) -> Optional[str]:
    """
    Get ISO post creation date from a post URN (when ID is Snowflake-encoded).

    Returns None for comment URNs or when ID format doesn't support extraction.

    Args:
        urn: e.g. urn:li:ugcPost:7398404729531285504

    Returns:
        ISO 8601 string (e.g. "2024-02-15T10:30:00+00:00") or None
    """
    if not urn or "urn:li:comment:" in urn:
        return None
    raw_id = extract_urn_id(urn)
    if not raw_id:
        return None
    # Comment URNs yield "activity:123,456" - skip
    if ":" in raw_id or "," in raw_id:
        return None
    ts_ms = timestamp_ms_from_linkedin_id(raw_id)
    if ts_ms is None:
        return None
    return _ms_to_iso(ts_ms) or None
