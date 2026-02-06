"""
Local SQLite store for extraction review items.

Persists raw elements, extracted output, status, notes, and corrections
under outputs/review/. Work queue includes pending, needs_fix, and skipped
so you can revisit skipped items later.
"""

import json
import sqlite3
from pathlib import Path
from typing import Any, List, Optional

from linkedin_api.extraction_preview import extract_element_preview
from linkedin_api.review_ids import compute_element_id

REVIEW_DIR = Path(__file__).resolve().parent.parent / "outputs" / "review"
DB_PATH = REVIEW_DIR / "review.sqlite3"

STATUS_PENDING = "pending"
STATUS_VALIDATED = "validated"
STATUS_SKIPPED = "skipped"
STATUS_NEEDS_FIX = "needs_fix"
STATUS_FIXED_VALIDATED = "fixed_validated"

WORK_QUEUE_STATUSES = (STATUS_PENDING, STATUS_NEEDS_FIX, STATUS_SKIPPED)


def _ensure_dir() -> None:
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)


def _get_conn() -> sqlite3.Connection:
    _ensure_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn: Optional[sqlite3.Connection] = None) -> None:
    """Create review_items table if it does not exist."""
    own = conn is None
    conn = conn or _get_conn()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS review_items (
                element_id TEXT PRIMARY KEY,
                processed_at INTEGER,
                resource_name TEXT,
                method_name TEXT,
                raw_json TEXT,
                extracted_json TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                notes TEXT,
                corrected_json TEXT,
                updated_at INTEGER
            )
            """
        )
        conn.commit()
    finally:
        if own:
            conn.close()


def upsert(
    element: dict,
    *,
    status: Optional[str] = None,
    notes: Optional[str] = None,
    corrected_json: Optional[dict] = None,
) -> str:
    """
    Insert or update a review item from a raw changelog element.

    If the element_id already exists, updates raw_json and extracted_json only
    when raw_json is different; status/notes/corrected_json are updated when provided.

    Returns:
        element_id
    """
    element_id = compute_element_id(element)
    raw_json_str = json.dumps(element, default=str)
    preview = extract_element_preview(element)
    extracted_json_str = json.dumps(preview["extracted"], default=str)
    processed_at = element.get("processedAt")
    resource_name = element.get("resourceName") or ""
    method_name = element.get("methodName") or ""

    conn = _get_conn()
    try:
        init_schema(conn)
        row = conn.execute(
            "SELECT raw_json, status, notes, corrected_json FROM review_items WHERE element_id = ?",
            (element_id,),
        ).fetchone()

        if row is None:
            conn.execute(
                """
                INSERT INTO review_items
                (element_id, processed_at, resource_name, method_name, raw_json, extracted_json, status, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, strftime('%s','now'))
                """,
                (
                    element_id,
                    processed_at,
                    resource_name,
                    method_name,
                    raw_json_str,
                    extracted_json_str,
                    status or STATUS_PENDING,
                ),
            )
        else:
            updates = [
                "raw_json = ?",
                "extracted_json = ?",
                "processed_at = ?",
                "updated_at = strftime('%s','now')",
            ]
            params: List[Any] = [raw_json_str, extracted_json_str, processed_at]
            if status is not None:
                updates.append("status = ?")
                params.append(status)
            if notes is not None:
                updates.append("notes = ?")
                params.append(notes)
            if corrected_json is not None:
                updates.append("corrected_json = ?")
                params.append(json.dumps(corrected_json, default=str))
            params.append(element_id)
            conn.execute(
                f"UPDATE review_items SET {', '.join(updates)} WHERE element_id = ?",
                params,
            )
        conn.commit()
        return element_id
    finally:
        conn.close()


def get_work_queue() -> List[dict]:
    """
    Return review items with status in (pending, needs_fix, skipped), ordered by processed_at.

    Each item is a dict with element_id, processed_at, resource_name, method_name,
    raw_json (parsed), extracted_json (parsed), status, notes, corrected_json (parsed).
    """
    conn = _get_conn()
    try:
        placeholders = ",".join("?" * len(WORK_QUEUE_STATUSES))
        rows = conn.execute(
            f"""
            SELECT element_id, processed_at, resource_name, method_name, raw_json,
                   extracted_json, status, notes, corrected_json, updated_at
            FROM review_items
            WHERE status IN ({placeholders})
            ORDER BY processed_at ASC NULLS LAST, element_id
            """,
            WORK_QUEUE_STATUSES,
        ).fetchall()
        out = []
        for r in rows:
            raw = json.loads(r["raw_json"]) if r["raw_json"] else {}
            extracted = json.loads(r["extracted_json"]) if r["extracted_json"] else {}
            corrected = json.loads(r["corrected_json"]) if r["corrected_json"] else None
            out.append(
                {
                    "element_id": r["element_id"],
                    "processed_at": r["processed_at"],
                    "resource_name": r["resource_name"],
                    "method_name": r["method_name"],
                    "raw_json": raw,
                    "extracted_json": extracted,
                    "status": r["status"],
                    "notes": r["notes"],
                    "corrected_json": corrected,
                    "updated_at": r["updated_at"],
                }
            )
        return out
    finally:
        conn.close()


def sync_elements(elements: List[dict]) -> int:
    """
    Upsert all elements into the store (insert or update raw/extracted only).
    Does not overwrite status, notes, or corrected_json for existing rows.

    Returns:
        Number of elements synced (inserted or updated raw/extracted).
    """
    _ensure_dir()
    conn = _get_conn()
    try:
        init_schema(conn)
        count = 0
        for element in elements:
            element_id = compute_element_id(element)
            raw_json_str = json.dumps(element, default=str)
            preview = extract_element_preview(element)
            extracted_json_str = json.dumps(preview["extracted"], default=str)
            processed_at = element.get("processedAt")
            resource_name = element.get("resourceName") or ""
            method_name = element.get("methodName") or ""

            row = conn.execute(
                "SELECT element_id FROM review_items WHERE element_id = ?",
                (element_id,),
            ).fetchone()
            if row is None:
                conn.execute(
                    """
                    INSERT INTO review_items
                    (element_id, processed_at, resource_name, method_name, raw_json, extracted_json, status, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, strftime('%s','now'))
                    """,
                    (
                        element_id,
                        processed_at,
                        resource_name,
                        method_name,
                        raw_json_str,
                        extracted_json_str,
                        STATUS_PENDING,
                    ),
                )
                count += 1
        conn.commit()
        return count
    finally:
        conn.close()


def update_status(element_id: str, status: str) -> None:
    """Set status for a review item."""
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE review_items SET status = ?, updated_at = strftime('%s','now') WHERE element_id = ?",
            (status, element_id),
        )
        conn.commit()
    finally:
        conn.close()


def update_correction(
    element_id: str,
    corrected_json: Optional[dict] = None,
    notes: Optional[str] = None,
    status: Optional[str] = None,
) -> None:
    """Update corrected_json and/or notes and/or status for a review item."""
    conn = _get_conn()
    try:
        updates = ["updated_at = strftime('%s','now')"]
        params: List[Any] = []
        if corrected_json is not None:
            updates.append("corrected_json = ?")
            params.append(json.dumps(corrected_json, default=str))
        if notes is not None:
            updates.append("notes = ?")
            params.append(notes)
        if status is not None:
            updates.append("status = ?")
            params.append(status)
        params.append(element_id)
        conn.execute(
            f"UPDATE review_items SET {', '.join(updates)} WHERE element_id = ?",
            params,
        )
        conn.commit()
    finally:
        conn.close()


def get_item(element_id: str) -> Optional[dict]:
    """Return a single review item by element_id, or None."""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT element_id, processed_at, resource_name, method_name, raw_json, "
            "extracted_json, status, notes, corrected_json, updated_at "
            "FROM review_items WHERE element_id = ?",
            (element_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "element_id": row["element_id"],
            "processed_at": row["processed_at"],
            "resource_name": row["resource_name"],
            "method_name": row["method_name"],
            "raw_json": json.loads(row["raw_json"]) if row["raw_json"] else {},
            "extracted_json": (
                json.loads(row["extracted_json"]) if row["extracted_json"] else {}
            ),
            "status": row["status"],
            "notes": row["notes"],
            "corrected_json": (
                json.loads(row["corrected_json"]) if row["corrected_json"] else None
            ),
            "updated_at": row["updated_at"],
        }
    finally:
        conn.close()


def get_fixture_items() -> List[dict]:
    """Return items that have corrected_json set (for export fixtures)."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT element_id, raw_json, corrected_json FROM review_items "
            "WHERE corrected_json IS NOT NULL AND corrected_json != ''"
        ).fetchall()
        return [
            {
                "element_id": r["element_id"],
                "raw_element": json.loads(r["raw_json"]) if r["raw_json"] else {},
                "expected_extracted": (
                    json.loads(r["corrected_json"]) if r["corrected_json"] else {}
                ),
            }
            for r in rows
        ]
    finally:
        conn.close()


def export_fixtures(fixtures_dir: Optional[Path] = None) -> int:
    """
    Write JSON fixtures to outputs/review/fixtures/ for items with corrected_json.

    Returns:
        Number of fixture files written.
    """
    fixtures_dir = fixtures_dir or REVIEW_DIR / "fixtures"
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    items = get_fixture_items()
    for i, item in enumerate(items):
        path = fixtures_dir / f"{item['element_id']}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "raw_element": item["raw_element"],
                    "expected_extracted": item["expected_extracted"],
                },
                f,
                indent=2,
                default=str,
            )
    return len(items)
