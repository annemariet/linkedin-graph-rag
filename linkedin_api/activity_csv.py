"""
Activity record model and CSV serialization.

The master CSV at ``get_data_dir() / "activities.csv"`` is the canonical
append-only local cache of all Portability API data.  It is shared across
pipelines (Neo4j graph builder, MVP summarizer, etc.).

CSV columns
-----------
owner            API user's URN
activity_type    post | comment | repost | instant_repost | reaction_to_post
                 | reaction_to_comment
time             Epoch milliseconds
reaction_type    LIKE | PRAISE | ... (empty for non-reactions)
author_urn       Person who performed the action
activity_urn     Post / Comment URN
post_url         LinkedIn URL
content          Post / comment text (from API)
parent_urn       Parent post / comment URN (for comments, reposts)
original_post_urn  Original post URN (for reposts)
created_at       ISO timestamp
"""

from __future__ import annotations

import csv
import io
import os
from dataclasses import asdict, dataclass, fields
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Sequence


# -- ActivityType enum -----------------------------------------------------


class ActivityType(str, Enum):
    """Recognised activity types in the CSV."""

    POST = "post"
    COMMENT = "comment"
    REPOST = "repost"
    INSTANT_REPOST = "instant_repost"
    REACTION_TO_POST = "reaction_to_post"
    REACTION_TO_COMMENT = "reaction_to_comment"


# -- ActivityRecord dataclass ----------------------------------------------

CSV_COLUMNS = [
    "owner",
    "activity_type",
    "time",
    "reaction_type",
    "author_urn",
    "activity_urn",
    "post_url",
    "content",
    "parent_urn",
    "original_post_urn",
    "created_at",
]


@dataclass
class ActivityRecord:
    """One row in the master activities CSV."""

    owner: str = ""
    activity_type: str = ""
    time: str = ""  # epoch ms as string (CSV-safe)
    reaction_type: str = ""
    author_urn: str = ""
    activity_urn: str = ""
    post_url: str = ""
    content: str = ""
    parent_urn: str = ""
    original_post_urn: str = ""
    created_at: str = ""

    def to_row(self) -> dict[str, str]:
        """Return an ordered dict suitable for ``csv.DictWriter``."""
        d = asdict(self)
        return {col: str(d.get(col, "") or "") for col in CSV_COLUMNS}

    @classmethod
    def from_row(cls, row: dict[str, str]) -> "ActivityRecord":
        """Create an ActivityRecord from a CSV row dict."""
        valid_fields = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in row.items() if k in valid_fields}
        return cls(**filtered)


# -- Canonical data directory ----------------------------------------------


def get_data_dir() -> Path:
    """Return the canonical data directory for LinkedIn API data.

    Uses ``LINKEDIN_DATA_DIR`` env var if set, otherwise
    ``~/.linkedin_api/data/``.  This ensures a single shared location
    across worktrees.
    """
    env = os.getenv("LINKEDIN_DATA_DIR")
    if env:
        data_dir = Path(env)
    else:
        data_dir = Path.home() / ".linkedin_api" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_default_csv_path() -> Path:
    """Return the default path for the master activities CSV."""
    return get_data_dir() / "activities.csv"


# -- CSV I/O ---------------------------------------------------------------


def _write_header(path: Path) -> None:
    """Write the CSV header row if the file does not exist or is empty."""
    if path.exists() and path.stat().st_size > 0:
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()


def _load_existing_urns(path: Path) -> set[str]:
    """Return the set of activity_urn values already in *path*."""
    if not path.exists() or path.stat().st_size == 0:
        return set()
    urns: set[str] = set()
    with open(path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            urn = row.get("activity_urn", "")
            if urn:
                urns.add(urn)
    return urns


def append_records_csv(
    records: Sequence[ActivityRecord],
    path: Path | None = None,
) -> int:
    """Append *records* to the CSV at *path*, deduplicating by ``activity_urn``.

    Returns the number of new records actually written.
    """
    if path is None:
        path = get_default_csv_path()

    _write_header(path)
    existing = _load_existing_urns(path)

    new_records = [
        r for r in records if r.activity_urn and r.activity_urn not in existing
    ]
    if not new_records:
        return 0

    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        for rec in new_records:
            writer.writerow(rec.to_row())

    return len(new_records)


def load_records_csv(path: Path | None = None) -> list[ActivityRecord]:
    """Read all records from the CSV at *path*.

    Returns an empty list when the file does not exist.
    """
    if path is None:
        path = get_default_csv_path()

    if not path.exists() or path.stat().st_size == 0:
        return []

    records: list[ActivityRecord] = []
    with open(path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append(ActivityRecord.from_row(row))
    return records


def records_to_csv_string(records: Sequence[ActivityRecord]) -> str:
    """Serialize *records* to a CSV string (useful for tests)."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    for rec in records:
        writer.writerow(rec.to_row())
    return buf.getvalue()


# -- Filtering helpers -----------------------------------------------------


def filter_by_date(
    records: list[ActivityRecord],
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[ActivityRecord]:
    """Filter records by date range using the ``created_at`` ISO field.

    Both *start* and *end* are inclusive.  ``None`` means unbounded.
    """
    result: list[ActivityRecord] = []
    for rec in records:
        if not rec.created_at:
            continue
        try:
            dt = datetime.fromisoformat(rec.created_at)
        except (ValueError, TypeError):
            continue
        if start and dt < start:
            continue
        if end and dt > end:
            continue
        result.append(rec)
    return result


def filter_by_type(
    records: list[ActivityRecord],
    activity_type: ActivityType | str,
) -> list[ActivityRecord]:
    """Filter records by activity type."""
    type_str = (
        activity_type.value
        if isinstance(activity_type, ActivityType)
        else str(activity_type)
    )
    return [r for r in records if r.activity_type == type_str]
