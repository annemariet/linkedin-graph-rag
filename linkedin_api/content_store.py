"""File-based content storage for external post/comment text.

Stores content of *other people's posts* that the user interacted with
(reacted to, commented on).  The user's own content (posts they wrote,
comments they wrote) lives in the CSV ``content`` column.

Files are stored under ``get_data_dir() / "content/"`` and named by the
SHA-256 hash of the activity URN.

Content sourcing priority (handled by callers):
1. Portability API text (when available for own content -- already in CSV)
2. ``browser-use`` for JS-rendered LinkedIn pages
3. ``requests`` + BeautifulSoup fallback
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from linkedin_api.activity_csv import get_data_dir


def _content_dir() -> Path:
    """Return (and create) the content storage directory."""
    d = get_data_dir() / "content"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _urn_to_filename(urn: str) -> str:
    """Derive a safe filename from an activity URN."""
    return hashlib.sha256(urn.encode()).hexdigest() + ".txt"


def save_content(urn: str, text: str) -> Path:
    """Persist *text* for *urn*.  Returns the file path written."""
    if not urn or not text:
        raise ValueError("Both urn and text must be non-empty")
    path = _content_dir() / _urn_to_filename(urn)
    path.write_text(text, encoding="utf-8")
    return path


def load_content(urn: str) -> str | None:
    """Load stored content for *urn*, or ``None`` if not found."""
    if not urn:
        return None
    path = _content_dir() / _urn_to_filename(urn)
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def has_content(urn: str) -> bool:
    """Return ``True`` if content has been stored for *urn*."""
    if not urn:
        return False
    return (_content_dir() / _urn_to_filename(urn)).exists()


def content_path(urn: str) -> Path:
    """Return the file path where content for *urn* would be stored."""
    return _content_dir() / _urn_to_filename(urn)
