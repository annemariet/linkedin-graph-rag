"""File-based content storage for post/comment text (Markdown).

Stores the full content of any post or comment by URN, including both
the user's own content and other people's posts they interacted with.
The user's own text is also in the CSV ``content`` column, but the
content store is the canonical source for enrichment and indexing.

Files are stored under ``get_data_dir() / "content/"`` as Markdown,
named by the SHA-256 hash of the activity URN.

Content sourcing priority (handled by callers):
1. Portability API text (available for own content at extraction time)
2. ``requests`` + HTML-to-Markdown for public posts
3. ``browser-use`` when login is required (e.g. private posts)

Phase 3 metadata (summary, topics, etc.) stored as ``{hash}.meta.json`` sidecar.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from linkedin_api.activity_csv import get_data_dir


def _content_dir() -> Path:
    """Return (and create) the content storage directory."""
    d = get_data_dir() / "content"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _urn_to_filename(urn: str) -> str:
    """Derive a safe filename from an activity URN."""
    return hashlib.sha256(urn.encode()).hexdigest() + ".md"


def _urn_to_stem(urn: str) -> str:
    """Filename stem (for registry and .meta.json sidecar)."""
    return _urn_to_filename(urn).removesuffix(".md")


def _meta_path(urn: str) -> Path:
    return _content_dir() / f"{_urn_to_stem(urn)}.meta.json"


def save_content(urn: str, text: str) -> Path:
    """Persist *text* for *urn*.  Returns the file path written."""
    if not urn or not text:
        raise ValueError("Both urn and text must be non-empty")
    path = _content_dir() / _urn_to_filename(urn)
    path.write_text(text, encoding="utf-8")
    _register_urn(urn)
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


# --- Phase 3 metadata (summary, topics, etc.) ---

_META_KEYS = (
    "summary",
    "topics",
    "technologies",
    "people",
    "category",
    "urls",
    "post_url",
    "summarized_at",
)


def save_metadata(
    urn: str,
    summary: str = "",
    topics: list[str] | None = None,
    technologies: list[str] | None = None,
    people: list[str] | None = None,
    category: str | None = None,
    urls: list[str] | None = None,
    post_url: str = "",
    **extra: Any,
) -> Path:
    """Save metadata for urn. Overwrites existing."""
    meta = {
        "summary": summary,
        "topics": topics or [],
        "technologies": technologies or [],
        "people": people or [],
        "category": category or "",
        "urls": urls or [],
        "post_url": post_url or "",
        **{k: v for k, v in extra.items() if k in _META_KEYS},
    }
    path = _meta_path(urn)
    path.write_text(json.dumps(meta, indent=0), encoding="utf-8")
    return path


def update_summary_metadata(
    urn: str,
    summary: str,
    topics: list[str],
    technologies: list[str],
    people: list[str],
    category: str | None,
) -> Path:
    """Update metadata with LLM summary. Preserves urls, post_url from enrichment."""
    meta = dict(load_metadata(urn) or {})
    meta["summary"] = summary
    meta["topics"] = topics
    meta["technologies"] = technologies
    meta["people"] = people
    meta["category"] = category or ""
    meta["summarized_at"] = datetime.now(timezone.utc).isoformat()
    path = _meta_path(urn)
    path.write_text(json.dumps(meta, indent=0), encoding="utf-8")
    return path


def load_metadata(urn: str) -> dict[str, Any] | None:
    """Load metadata for urn, or None if not found."""
    if not urn:
        return None
    path = _meta_path(urn)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def has_metadata(urn: str) -> bool:
    """True if metadata exists for urn."""
    return urn and _meta_path(urn).exists()


def needs_summary(urn: str) -> bool:
    """True if urn has content but no metadata (or empty summary)."""
    if not has_content(urn):
        return False
    meta = load_metadata(urn)
    if meta is None:
        return True
    return not (meta.get("summary") or "").strip()


def list_posts_needing_summary(limit: int | None = None) -> list[dict[str, Any]]:
    """URNs with content (≥50 chars) but no summary. Returns [{urn, content}, ...]."""
    out: list[dict[str, Any]] = []
    content_dir = _content_dir()
    for path in sorted(content_dir.glob("*.md")):
        stem = path.stem
        content = path.read_text(encoding="utf-8")
        if len(content) < 50:
            continue
        meta_path = content_dir / f"{stem}.meta.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if (meta.get("summary") or "").strip():
                continue
        urn = _stem_to_urn(stem)
        if urn:
            out.append({"urn": urn, "content": content})
        if limit and len(out) >= limit:
            break
    return out


def _stem_to_urn(stem: str) -> str | None:
    """Reverse lookup: stem -> urn via registry."""
    registry_path = _content_dir() / "_urn_registry.json"
    if not registry_path.exists():
        return None
    reg = json.loads(registry_path.read_text(encoding="utf-8"))
    return reg.get(stem)


def _register_urn(urn: str) -> None:
    """Register stem -> urn for reverse lookup."""
    registry_path = _content_dir() / "_urn_registry.json"
    reg = {}
    if registry_path.exists():
        reg = json.loads(registry_path.read_text(encoding="utf-8"))
    reg[_urn_to_stem(urn)] = urn
    registry_path.write_text(json.dumps(reg, indent=0), encoding="utf-8")
