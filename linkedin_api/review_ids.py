"""
Stable element IDs for extraction review persistence.

Computes a deterministic id from changelog element fields so we can
upsert and resume review state without duplicates.
"""

import hashlib
import json


def compute_element_id(element: dict) -> str:
    """
    Compute a stable id for a changelog element.

    Uses processedAt, resourceName, methodName, and best-available URN
    (activity.$URN, activity.id, activity.object), plus resourceUri/resourceId
    if present. Hash with SHA-256 and return hex prefix for brevity.

    Args:
        element: Raw changelog element dict.

    Returns:
        Short hex string (first 16 chars of SHA-256).
    """
    activity = element.get("activity") or {}
    urn = (
        activity.get("$URN")
        or activity.get("urn")
        or activity.get("id")
        or activity.get("object")
        or ""
    )
    if isinstance(urn, dict):
        urn = json.dumps(urn, sort_keys=True)
    else:
        urn = str(urn)

    parts = [
        str(element.get("processedAt") or ""),
        element.get("resourceName") or "",
        element.get("methodName") or "",
        urn,
        str(element.get("resourceUri") or ""),
        str(element.get("resourceId") or ""),
    ]
    canonical = "|".join(parts)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return digest[:16]
