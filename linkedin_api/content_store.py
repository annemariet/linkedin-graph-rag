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
(URLs requiring login are not enriched.)

Phase 3 metadata (summary, topics, etc.) stored as ``{hash}.meta.json`` sidecar.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from linkedin_api.activity_csv import get_data_dir
from linkedin_api.utils.urls import resolve_redirect


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
    "mentions",
    "tags",
    "post_url",
    "post_urn",
    "post_author",
    "post_author_url",
    "post_id",
    "activities_ids",
    "summarized_at",
    "activity_time_iso",
    "post_created_at",
)


def _merge_mentions(
    previous: list[dict[str, Any]] | None, incoming: list[dict[str, Any]] | None
) -> list[dict[str, str]]:
    """Union by ``url``; prefer non-empty ``name`` when merging."""
    by_url: dict[str, dict[str, str]] = {}
    for group in (previous or [], incoming or []):
        for raw in group:
            if not isinstance(raw, dict):
                continue
            url = str(raw.get("url") or "").strip()
            if not url:
                continue
            name = str(raw.get("name") or "").strip()
            if url not in by_url:
                by_url[url] = {"name": name, "url": url}
            elif name and not (by_url[url].get("name") or "").strip():
                by_url[url]["name"] = name
    return list(by_url.values())


def _merge_tags(previous: list[Any] | None, incoming: list[Any] | None) -> list[str]:
    prev = {str(x).strip() for x in (previous or []) if x and str(x).strip()}
    inc = {str(x).strip() for x in (incoming or []) if x and str(x).strip()}
    return sorted(prev | inc)


def resolve_urls_for_metadata(urls: list[str] | None) -> list[str]:
    """Return unique URLs after best-effort redirect resolution (see ``resolve_redirect``)."""
    if not urls:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for u in urls:
        s = (u or "").strip()
        if not s or s in seen:
            continue
        seen.add(s)
        try:
            resolved = resolve_redirect(s)
        except Exception:
            resolved = s
        if resolved not in seen:
            seen.add(resolved)
        out.append(resolved)
    return out


def _ms_to_iso(ts_ms: int | float | None) -> str:
    """Convert epoch ms to ISO string (human-readable)."""
    if ts_ms is None:
        return ""
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()


def _normalize_activity_time_iso(meta: dict) -> str:
    """Return activity_time_iso (ISO). Backward compat: reaction_created_at, reaction_timestamp_ms."""
    iso = (
        meta.get("activity_time_iso") or meta.get("reaction_created_at") or ""
    ).strip()
    if iso:
        return iso
    ts = meta.get("reaction_timestamp_ms")
    if ts is not None and isinstance(ts, (int, float)):
        return _ms_to_iso(int(ts))
    return ""


def _iso_to_ms(iso_str: str | None) -> int | None:
    """Parse ISO string to epoch ms for sorting. Returns None if invalid."""
    s = (iso_str or "").strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000)
    except (ValueError, TypeError):
        return None


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
    """Save metadata for *urn*.

    Merges with any existing file: ``activities_ids`` are unioned in order;
    ``post_id``, ``post_urn``, and ``post_author_url`` are kept from the
    previous file when the new values are empty. ``urls`` are de-duplicated
    and passed through ``resolve_urls_for_metadata``.
    """
    existing = dict(load_metadata(urn) or {})
    from_extra = {k: v for k, v in extra.items() if k in _META_KEYS}
    meta: dict[str, Any] = {
        "summary": summary,
        "topics": topics or [],
        "technologies": technologies or [],
        "people": people or [],
        "category": category or "",
        "urls": urls or [],
        "mentions": [],
        "tags": [],
        "post_url": post_url or "",
        "post_urn": "",
        "post_author": "",
        "post_author_url": "",
        "post_id": "",
        "activities_ids": [],
        "summarized_at": existing.get("summarized_at") or "",
        "activity_time_iso": "",
        "post_created_at": "",
    }
    meta.update({k: v for k, v in existing.items() if k in _META_KEYS})
    meta.update(from_extra)
    meta["summary"] = summary
    meta["topics"] = topics or []
    meta["technologies"] = technologies or []
    meta["people"] = people or []
    meta["category"] = category or ""
    meta["urls"] = resolve_urls_for_metadata(urls or [])
    prev_mentions = (
        existing.get("mentions") if isinstance(existing.get("mentions"), list) else None
    )
    prev_tags = existing.get("tags")
    meta["mentions"] = _merge_mentions(
        prev_mentions,
        meta.get("mentions") if isinstance(meta.get("mentions"), list) else None,
    )
    meta["tags"] = _merge_tags(
        prev_tags if isinstance(prev_tags, list) else None,
        meta.get("tags") if isinstance(meta.get("tags"), list) else None,
    )
    meta["post_url"] = post_url or meta.get("post_url") or ""

    prev_ids = existing.get("activities_ids") or []
    if not isinstance(prev_ids, list):
        prev_ids = [str(prev_ids)]
    else:
        prev_ids = [str(x) for x in prev_ids if x]
    new_ids = meta.get("activities_ids") or []
    if not isinstance(new_ids, list):
        new_ids = [str(new_ids)]
    else:
        new_ids = [str(x) for x in new_ids if x]
    meta["activities_ids"] = list(dict.fromkeys(prev_ids + new_ids))

    for k in ("post_id", "post_urn", "post_author_url"):
        if not (str(meta.get(k) or "")).strip() and existing.get(k):
            meta[k] = existing[k]

    if not (str(meta.get("post_created_at") or "")).strip() and existing.get(
        "post_created_at"
    ):
        meta["post_created_at"] = existing["post_created_at"]
    if not (str(meta.get("activity_time_iso") or "")).strip() and existing.get(
        "activity_time_iso"
    ):
        meta["activity_time_iso"] = existing["activity_time_iso"]

    path = _meta_path(urn)
    path.write_text(json.dumps(meta, indent=0), encoding="utf-8")
    return path


def update_urls_metadata(urn: str, urls: list[str]) -> Path:
    """Update only the ``urls`` field in metadata, preserving all other fields.

    Creates a minimal metadata record if none exists yet. URLs are resolved
    via ``resolve_urls_for_metadata``.
    """
    meta = dict(load_metadata(urn) or {})
    meta["urls"] = resolve_urls_for_metadata(urls)
    path = _meta_path(urn)
    path.write_text(json.dumps(meta, indent=0), encoding="utf-8")
    return path


def update_metadata_fields(urn: str, **kwargs: Any) -> Path:
    """Merge specified metadata fields, preserving others. Only _META_KEYS are applied."""
    meta = dict(load_metadata(urn) or {})
    for k, v in kwargs.items():
        if k in _META_KEYS:
            meta[k] = v
    path = _meta_path(urn)
    path.write_text(json.dumps(meta, indent=0), encoding="utf-8")
    return path


def merge_post_identity(
    urn: str,
    *,
    post_id: str = "",
    post_urn: str = "",
    extra_activity_ids: list[str] | None = None,
) -> Path | None:
    """
    Fill identity fields from CSV without touching summary/topics or re-resolving ``urls``.

    - Sets ``post_id`` / ``post_urn`` when currently empty.
    - Unions ``activities_ids`` with *extra_activity_ids* (order preserved, de-duplicated).

    Returns ``None`` if there is no metadata file or nothing would change.
    """
    existing = load_metadata(urn)
    if existing is None:
        return None
    meta = dict(existing)
    pid = (post_id or "").strip()
    if pid and not (str(meta.get("post_id") or "")).strip():
        meta["post_id"] = pid
    pu = (post_urn or "").strip()
    if pu and not (str(meta.get("post_urn") or "")).strip():
        meta["post_urn"] = pu

    prev = meta.get("activities_ids") or []
    if not isinstance(prev, list):
        prev = [str(prev)] if prev else []
    else:
        prev = [str(x) for x in prev if x]
    extra = extra_activity_ids or []
    extra = [str(x) for x in extra if x]
    meta["activities_ids"] = list(dict.fromkeys(prev + extra))

    if meta == existing:
        return None

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
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def has_metadata(urn: str) -> bool:
    """True if metadata exists for urn."""
    return bool(urn) and _meta_path(urn).exists()


def needs_summary(urn: str) -> bool:
    """True if urn has content but no metadata (or empty summary)."""
    if not has_content(urn):
        return False
    meta = load_metadata(urn)
    if meta is None:
        return True
    return not (meta.get("summary") or "").strip()


def _load_registry() -> dict[str, str]:
    """Load stem -> urn registry once. Returns {} if missing."""
    registry_path = _content_dir() / "_urn_registry.json"
    if not registry_path.exists():
        return {}
    data: dict[str, str] = json.loads(registry_path.read_text(encoding="utf-8"))
    return data


def list_summarized_metadata(limit: int | None = None) -> list[dict[str, Any]]:
    """All posts that have a non-empty summary. Returns list of metadata dicts with urn for content lookup."""
    out: list[dict[str, Any]] = []
    content_dir = _content_dir()
    registry = _load_registry()
    for path in sorted(content_dir.glob("*.meta.json")):
        try:
            stem = path.stem.removesuffix(".meta")  # hash from xyz.meta.json
            urn = registry.get(stem)
            meta = json.loads(path.read_text(encoding="utf-8"))
            if not (meta.get("summary") or "").strip():
                continue
            act_ids = meta.get("activities_ids") or []
            if not isinstance(act_ids, list):
                act_ids = []
            out.append(
                {
                    "urn": urn or "",
                    "summary": (meta.get("summary") or "").strip(),
                    "topics": meta.get("topics") or [],
                    "technologies": meta.get("technologies") or [],
                    "people": meta.get("people") or [],
                    "category": meta.get("category") or "",
                    "summarized_at": meta.get("summarized_at") or "",
                    "post_url": meta.get("post_url") or "",
                    "post_urn": (meta.get("post_urn") or "").strip(),
                    "post_author": (meta.get("post_author") or "").strip(),
                    "post_author_url": (meta.get("post_author_url") or "").strip(),
                    "post_id": (meta.get("post_id") or "").strip(),
                    "activities_ids": [str(x) for x in act_ids if x],
                    "activity_time_iso": _normalize_activity_time_iso(meta),
                    "post_created_at": (meta.get("post_created_at") or "").strip(),
                }
            )
            if limit and len(out) >= limit:
                break
        except (json.JSONDecodeError, OSError):
            continue
    return out


def list_posts_needing_summary(limit: int | None = None) -> list[dict[str, Any]]:
    """URNs with content (≥50 chars) but no summary. Returns [{urn, content}, ...]."""
    out: list[dict[str, Any]] = []
    content_dir = _content_dir()
    registry = _load_registry()
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
        urn = registry.get(stem)
        if urn:
            out.append({"urn": urn, "content": content})
        if limit and len(out) >= limit:
            break
    return out


def _register_urn(urn: str) -> None:
    """Register stem -> urn for reverse lookup."""
    registry_path = _content_dir() / "_urn_registry.json"
    reg = {}
    if registry_path.exists():
        reg = json.loads(registry_path.read_text(encoding="utf-8"))
    reg[_urn_to_stem(urn)] = urn
    registry_path.write_text(json.dumps(reg, indent=0), encoding="utf-8")
