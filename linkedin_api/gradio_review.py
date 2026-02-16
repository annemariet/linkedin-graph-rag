"""
Gradio UI for reviewing extraction of Portability API changelog elements.

Loads elements on start, syncs to local SQLite, and lets you review one-by-one
with Neo4j-style property cards, trace, validate/skip/incorrect, and correction editing.
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, List, Optional, Tuple

import gradio as gr

from linkedin_api.enrich_profiles import (
    _normalize_post_url,
    extract_author_profile_with_details,
    fetch_post_page,
    get_thumbnail_path_for_url,
    is_author_enrichment_enabled,
    parse_comment_author_from_html,
)
from linkedin_api.extract_resources import extract_urls_from_text
from linkedin_api.extract_graph_data import get_all_post_activities
from linkedin_api.extraction_preview import extract_element_preview
from linkedin_api.utils.changelog import (
    DEFAULT_START_TIME,
    TokenExpiredError,
    get_last_processed_timestamp,
)
from linkedin_api.review_store import (
    STATUS_FIXED_VALIDATED,
    STATUS_NEEDS_FIX,
    STATUS_PENDING,
    STATUS_SKIPPED,
    STATUS_VALIDATED,
    export_fixtures,
    get_item,
    get_work_queue,
    sync_elements,
    update_correction,
    update_status,
)

logger = logging.getLogger(__name__)


def _escape_md(s: str) -> str:
    """Escape backticks and backslashes so text is safe inside Markdown code."""
    if not isinstance(s, str):
        s = str(s)
    return s.replace("\\", "\\\\").replace("`", "\\`")


def _sanitize_for_json(obj: Any) -> Any:
    """Return a JSON-safe copy (string keys, no non-serializable values) for gr.JSON."""
    try:
        return json.loads(json.dumps(obj, default=str))
    except (TypeError, ValueError):
        return {"_error": "Could not serialize raw element"}


def _format_prop_value_for_cards(v: Any) -> str:
    """Format a property value for display; URLs become clickable Markdown links."""
    if isinstance(v, list):
        parts = []
        for x in v:
            if isinstance(x, str) and x.startswith("http"):
                parts.append(f"[{_escape_md(x)}]({x})")
            else:
                parts.append(_escape_md(str(x)))
        return ", ".join(parts)
    if isinstance(v, dict):
        return _escape_md(
            json.dumps(v)[:80] + ("..." if len(json.dumps(v)) > 80 else "")
        )
    if isinstance(v, str) and v.startswith("http"):
        return f"[{_escape_md(v)}]({v})"
    return _escape_md(str(v))


def _extracted_to_markdown_cards(
    extracted: dict, author_info: str = None, resources_info: str = None
) -> str:
    """Render extracted nodes and relationships as Neo4j-style Markdown property cards."""
    nodes = extracted.get("nodes", [])
    relationships = extracted.get("relationships", [])
    primary = extracted.get("primary", "")
    resource_name = extracted.get("resource_name", "")
    lines = [
        f"**Reviewing:** **{_escape_md(primary)}**",
        f"Resource: `{_escape_md(resource_name)}`",
        "",
        "_Corrections replace the extracted nodes/relationships for this element and are used when "
        "exporting fixtures and re-running the pipeline._",
        "",
        "**Neo4j nodes and relationships**",
        "",
    ]

    for node in nodes:
        label = node.get("label", "Node")
        props = node.get("properties", {})
        lines.append(f"**({label})**")
        for k, v in sorted(props.items()):
            val_str = _format_prop_value_for_cards(v)
            lines.append(f"  `{_escape_md(str(k))}`: {val_str}")
        lines.append("")

    if relationships:
        lines.append("**Relationships**")
        for rel in relationships:
            rtype = rel.get("type", "REL")
            from_urn = rel.get("from", "")[:40]
            to_urn = rel.get("to", "")[:40]
            props = rel.get("properties", {})
            prop_str = (" " + json.dumps(props)) if props else ""
            lines.append(
                f"  `{_escape_md(from_urn)}...` -[:{rtype}]-> `{_escape_md(to_urn)}...`"
            )
            if prop_str:
                lines.append(f"    props: `{_escape_md(prop_str.strip())}`")
        lines.append("")

    if extracted.get("skipped_reasons"):
        lines.append("**Skipped reasons**")
        for k, v in extracted["skipped_reasons"].items():
            lines.append(f"  - {k}: {v}")

    # Add enrichment info if available
    if (
        author_info
        and author_info != "No item."
        and "Click 'Extract author'" not in author_info
    ):
        lines.append("")
        lines.append("**Author (enriched)**")
        lines.append("```")
        lines.append(author_info)
        lines.append("```")

    if resources_info and resources_info != "No item.":
        lines.append("")
        lines.append("**Resources (enriched)**")
        lines.append("```")
        lines.append(resources_info)
        lines.append("```")

    return "\n".join(lines) if lines else "_No entities extracted_"


def _trace_to_markdown(trace: List[dict]) -> str:
    """Format trace as field <- json_path list. Escapes content so Markdown does not break."""
    if not trace:
        return "_No trace (run extraction for this element type)_"
    lines = []
    for t in trace:
        path = t.get("json_path", "")
        field = t.get("field_name", "")
        val = t.get("value_used", "")
        if len(str(val)) > 60:
            val = str(val)[:60] + "..."
        lines.append(
            f"- **{_escape_md(field)}** \u2190 `{_escape_md(str(path))}` `{_escape_md(str(val))}`"
        )
    return "\n".join(lines)


def _get_post_url_from_extracted(extracted: dict) -> Optional[str]:
    """Get first Post node URL from extracted for enrichment preview."""
    for node in extracted.get("nodes", []):
        if node.get("label") == "Post":
            url = (node.get("properties") or {}).get("url")
            if url:
                return url
    return None


def _get_content_from_extracted(extracted: dict) -> str:
    """Get first content/text from Post or Comment for resource extraction."""
    for node in extracted.get("nodes", []):
        props = node.get("properties") or {}
        if node.get("label") == "Post" and props.get("content"):
            return props.get("content", "")
        if node.get("label") == "Comment" and props.get("text"):
            return props.get("text", "")
    return ""


def _get_post_url_from_raw(raw: dict) -> Optional[str]:
    """Get post URL from raw changelog element (activity.id, root, or object → feed URL)."""
    activity = raw.get("activity") or {}
    for key in ("id", "root", "object"):
        post_urn = activity.get(key, "")
        if post_urn and isinstance(post_urn, str) and post_urn.startswith("urn:li:"):
            return f"https://www.linkedin.com/feed/update/{post_urn}"
    return None


def _format_author_result(details: dict) -> str:
    """Format extract_author_profile_with_details result for the UI."""
    lines = []
    lines.append(f"URL tried: {details.get('url_tried') or '(none)'}")
    if details.get("normalized_url") and details["normalized_url"] != details.get(
        "url_tried"
    ):
        lines.append(f"Normalized URL (fetched): {details['normalized_url']}")
    if details.get("from_cache"):
        lines.append("(from cache)")
    if details.get("status_code") is not None:
        lines.append(
            f"HTTP status: {details['status_code']}"
            + (" (404 Not Found)" if details["status_code"] == 404 else "")
        )
    if details.get("skip_reason"):
        lines.append(f"Result: {details['skip_reason']}")
        return "\n".join(lines)
    if details.get("author"):
        lines.append("Author:")
        try:
            lines.append(json.dumps(details["author"], indent=2, default=str))
        except (TypeError, ValueError):
            lines.append(str(details["author"]))
        return "\n".join(lines)
    if details.get("error"):
        lines.append(f"Result: {details['error']}")
        return "\n".join(lines)
    lines.append("Result: Could not extract author.")
    return "\n".join(lines)


def _format_resources_result(
    content: str, urls: list, content_source: str = "extracted/raw"
) -> str:
    """Format resources extraction for the UI (content snippet + URLs or message)."""
    lines = []
    if content:
        snippet = content[:400] + ("..." if len(content) > 400 else "")
        lines.append(f"Content used ({content_source}):")
        lines.append(snippet)
        lines.append("")
    else:
        lines.append("Content used: No post/comment text in extracted data or raw API.")
        lines.append("")
    if urls:
        lines.append("URLs found:")
        lines.extend(urls)
    else:
        lines.append("URLs found: None.")
    return "\n".join(lines)


def _get_content_from_raw(raw: dict) -> str:
    """Get full post or comment text from raw changelog element (API content)."""
    activity = raw.get("activity") or {}
    share = (activity.get("specificContent") or {}).get(
        "com.linkedin.ugc.ShareContent", {}
    )
    commentary = (share.get("shareCommentary") or {}).get("text", "")
    if commentary:
        return commentary
    comment_text = (activity.get("message") or {}).get("text", "")
    if comment_text:
        return comment_text
    return ""


def _get_comment_node_from_preview(preview: dict) -> Optional[Tuple[str, str, str]]:
    """Return (comment_urn, url, text) for the first Comment node, or None."""
    for node in preview.get("nodes", []):
        if node.get("label") == "Comment":
            props = node.get("properties") or {}
            urn = props.get("urn") or node.get("id")
            url = props.get("url") or ""
            text = props.get("text") or ""
            if urn and url:
                return (urn, url, text)
    return None


def _synthetic_person_urn(profile_url: str) -> str:
    """Stable URN for a person identified only by profile_url (e.g. from HTML)."""
    h = hashlib.sha256(profile_url.encode()).hexdigest()[:16]
    return f"urn:li:person:extracted_{h}"


def _apply_comment_author_to_payload(
    payload: dict, comment_urn: str, author_info: dict
) -> dict:
    """Add/update Person node and CREATES to Comment; remove old CREATES to this comment."""
    payload = json.loads(json.dumps(payload, default=str))
    nodes = list(payload.get("nodes", []))
    relationships = list(payload.get("relationships", []))
    person_urn = _synthetic_person_urn(author_info["profile_url"])
    person_id = person_urn.split(":")[-1]
    new_person = {
        "id": person_urn,
        "label": "Person",
        "properties": {
            "urn": person_urn,
            "person_id": person_id,
            "name": author_info["name"],
            "profile_url": author_info["profile_url"],
        },
    }
    if not any(n.get("id") == person_urn for n in nodes):
        nodes.append(new_person)
    relationships = [
        r
        for r in relationships
        if not (r.get("type") == "CREATES" and r.get("to") == comment_urn)
    ]
    relationships.append(
        {"type": "CREATES", "from": person_urn, "to": comment_urn, "properties": {}}
    )
    payload["nodes"] = nodes
    payload["relationships"] = relationships
    return payload


def _format_fetch_from(epoch_ms: int, source: str) -> str:
    """Human-readable 'fetch from' label (UTC)."""
    try:
        dt = datetime.fromtimestamp(epoch_ms / 1000.0, tz=timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC") + f" ({source})"
    except (ValueError, OSError):
        return f"{epoch_ms} ({source})"


def load_and_sync(start_time: Optional[int] = None) -> tuple:
    """
    Fetch changelog elements, sync to store, return (work_queue, status_message).
    When the API returns no new elements, still returns the existing work queue from the store.
    """
    try:
        # Treat 0 as "fetch from beginning" (ignore .last_run)
        api_start_time = start_time
        effective_start = start_time
        source = "your input"
        if effective_start is None:
            last_run = get_last_processed_timestamp()
            effective_start = last_run or DEFAULT_START_TIME
            api_start_time = effective_start
            source = ".last_run" if last_run else "default"
        elif effective_start == 0:
            effective_start = DEFAULT_START_TIME
            api_start_time = DEFAULT_START_TIME
            source = "default (fetch from beginning)"
        fetch_from_label = _format_fetch_from(effective_start, source)

        logger.info(
            "Load: fetching changelog from API (start_time=%s)...", api_start_time
        )
        elements = get_all_post_activities(start_time=api_start_time, verbose=False)
        logger.info(
            "Load: got %s elements, syncing to store...",
            len(elements) if elements else 0,
        )
        synced = sync_elements(elements) if elements else 0
        queue = get_work_queue()
        logger.info("Load: queue has %s items", len(queue))
        base = f"Fetch from: **{fetch_from_label}**. Work queue: {len(queue)} items (pending + needs_fix + skipped)."
        if not elements:
            hint = " Tip: enter Start time **0** to re-fetch from the beginning."
            return queue, f"No new elements from API. {base}{hint}"
        return queue, f"Synced {synced} elements. {base}"
    except TokenExpiredError:
        queue = get_work_queue()
        return (
            queue,
            "**Token expired.**\n\n"
            "1. Run `uv run python setup_token.py` and enter your new token.\n"
            "2. Set **LINKEDIN_ACCOUNT** the same everywhere (e.g. in `.env`: "
            "`LINKEDIN_ACCOUNT=your-email@example.com`). The app reads the token "
            "from keyring using this account; if it differs from when you ran "
            "setup_token, you get the old token.\n"
            "3. Restart the Gradio app, then Load again.\n"
            "4. Verify with `uv run python check_token.py` in the same terminal/env as the app.",
        )
    except Exception as e:
        logger.exception("Load and sync failed")
        return [], f"Error: {e}"


def select_item(queue: List[dict], index: int) -> dict:
    """Return queue[index] with clamped index."""
    if not queue:
        return {}
    idx = max(0, min(index, len(queue) - 1))
    return queue[idx]


def render_item(
    item: dict,
    show_extracted_json: bool,
    queue_len: int = 0,
    idx: int = 0,
    author_info: str = None,
    resources_info: str = None,
) -> tuple:
    """
    Return (cards_md, trace_md, raw_json, extracted_json_str, counter, correction_visible, corrected_json_str, notes).
    """
    if not item:
        return (
            "_No items in queue._",
            "",
            {},
            "{}",
            "0 / 0",
            False,
            "{}",
            "",
        )
    raw = item.get("raw_json") or {}
    extracted = item.get("extracted_json", {})
    corrected = item.get("corrected_json")
    status = item.get("status", STATUS_PENDING)
    notes = item.get("notes", "") or ""

    preview = extracted
    if corrected:
        preview = corrected

    cards_md = _extracted_to_markdown_cards(preview, author_info, resources_info)
    try:
        preview_result = extract_element_preview(raw)
        trace = preview_result.get("trace") or []
    except Exception:
        trace = []
    trace_md = _trace_to_markdown(trace)

    counter = f"{idx + 1} / {queue_len}" if queue_len else "0 / 0"

    correction_visible = status == STATUS_NEEDS_FIX
    corrected_str = json.dumps(
        corrected if corrected else extracted, indent=2, default=str
    )

    raw_safe = _sanitize_for_json(raw)
    return (
        cards_md,
        trace_md,
        raw_safe,
        json.dumps(extracted, indent=2, default=str),
        counter,
        correction_visible,
        corrected_str,
        notes,
    )


def _review_state_default():
    return {"queue": [], "index": 0}


def create_review_interface():
    """Build the Gradio Blocks interface for extraction review."""

    def _get_queue_index(state):
        if state is None or not isinstance(state, dict):
            return [], 0
        return state.get("queue") or [], state.get("index", 0)

    def on_load(start_time_str=None):
        start_time = None
        if start_time_str is not None and start_time_str.strip():
            try:
                start_time = int(start_time_str.strip())
            except ValueError:
                pass
        queue, msg = load_and_sync(start_time=start_time)
        if not queue:
            return (
                {"queue": [], "index": 0},
                msg,
                "_No items._",
                "",
                {},
                "0 / 0",
                "{}",
                "",
                "",
                "No item.",
                "No item.",
                None,
            )
        for i, q in enumerate(queue):
            q["_index"] = i
        item = queue[0]
        # Load enrichment (author, resources, thumbnail) by default now that thumbnails are fast
        author_text, resources_text, thumb_path = _enrichment_preview(
            item, include_thumbnail=True
        )
        cards, trace_md, raw, _ext_json, counter, _corr_vis, corr_str, notes = (
            render_item(item, False, len(queue), 0, author_text, resources_text)
        )
        return (
            {"queue": queue, "index": 0},
            msg,
            cards,
            trace_md,
            raw,
            counter,
            corr_str,
            notes,
            "",
            author_text,
            resources_text,
            thumb_path,
        )

    def on_prev(state):
        queue, index = _get_queue_index(state)
        if not queue:
            return (
                state,
                "_No items._",
                "",
                {},
                "0 / 0",
                "{}",
                "",
                "No item.",
                "No item.",
                None,
            )
        idx = max(0, index - 1)
        item = queue[idx]
        item["_index"] = idx
        author_text, resources_text, thumb_path = _enrichment_preview(
            item, include_thumbnail=True
        )
        cards, trace_md, raw, _ej, counter, _cv, corr_str, notes = render_item(
            item, False, len(queue), idx, author_text, resources_text
        )
        return (
            {"queue": queue, "index": idx},
            cards,
            trace_md,
            raw,
            counter,
            corr_str,
            notes,
            author_text,
            resources_text,
            thumb_path,
        )

    def on_next(state):
        queue, index = _get_queue_index(state)
        if not queue:
            return (
                state,
                "_No items._",
                "",
                {},
                "0 / 0",
                "{}",
                "",
                "No item.",
                "No item.",
                None,
            )
        idx = min(len(queue) - 1, index + 1)
        item = queue[idx]
        item["_index"] = idx
        author_text, resources_text, thumb_path = _enrichment_preview(
            item, include_thumbnail=True
        )
        cards, trace_md, raw, _ej, counter, _cv, corr_str, notes = render_item(
            item, False, len(queue), idx, author_text, resources_text
        )
        return (
            {"queue": queue, "index": idx},
            cards,
            trace_md,
            raw,
            counter,
            corr_str,
            notes,
            author_text,
            resources_text,
            thumb_path,
        )

    def on_validate(state):
        queue, index = _get_queue_index(state)
        if not queue or index >= len(queue):
            return (
                state,
                "_No items._",
                "",
                {},
                "0 / 0",
                "{}",
                "",
                "No item to validate.",
                "No item.",
                "No item.",
                None,
            )
        item = queue[index]
        eid = item["element_id"]
        update_status(eid, STATUS_VALIDATED)
        new_queue = get_work_queue()
        for i, q in enumerate(new_queue):
            q["_index"] = i
        if index >= len(new_queue):
            index = max(0, len(new_queue) - 1)
        if not new_queue:
            return (
                {"queue": [], "index": 0},
                "_No items._",
                "",
                {},
                "0 / 0",
                "{}",
                "",
                "Validated. Queue empty.",
                "No item.",
                "No item.",
                None,
            )
        item = new_queue[index]
        author_text, resources_text, thumb_path = _enrichment_preview(
            item, include_thumbnail=True
        )
        cards, trace_md, raw, _ej, counter, _cv, corr_str, notes = render_item(
            item, False, len(new_queue), index, author_text, resources_text
        )
        return (
            {"queue": new_queue, "index": index},
            cards,
            trace_md,
            raw,
            counter,
            corr_str,
            notes,
            "Validated.",
            author_text,
            resources_text,
            thumb_path,
        )

    def on_skip(state):
        queue, index = _get_queue_index(state)
        if not queue or index >= len(queue):
            return (
                state,
                "_No items._",
                "",
                {},
                "0 / 0",
                "{}",
                "",
                "No item to skip.",
                "No item.",
                "No item.",
                None,
            )
        item = queue[index]
        eid = item["element_id"]
        update_status(eid, STATUS_SKIPPED)
        new_queue = get_work_queue()
        for i, q in enumerate(new_queue):
            q["_index"] = i
        if index >= len(new_queue):
            index = max(0, len(new_queue) - 1)
        if not new_queue:
            return (
                {"queue": [], "index": 0},
                "_No items._",
                "",
                {},
                "0 / 0",
                "{}",
                "",
                "Skipped. Queue empty.",
                "No item.",
                "No item.",
                None,
            )
        item = new_queue[index]
        cards, trace_md, raw, _ej, counter, _cv, corr_str, notes = render_item(
            item, False, len(new_queue), index
        )
        author_text, resources_text, thumb_path = _enrichment_preview(
            item, include_thumbnail=True
        )
        return (
            {"queue": new_queue, "index": index},
            cards,
            trace_md,
            raw,
            counter,
            corr_str,
            notes,
            "Skipped.",
            author_text,
            resources_text,
            thumb_path,
        )

    def on_incorrect(state):
        queue, index = _get_queue_index(state)
        if not queue or index >= len(queue):
            return (
                state,
                "_No items._",
                "",
                {},
                "0 / 0",
                "{}",
                "",
                "No item.",
                "No item.",
                "No item.",
                None,
            )
        item = queue[index]
        eid = item["element_id"]
        update_status(eid, STATUS_NEEDS_FIX)
        extracted = item.get("extracted_json", {})
        update_correction(eid, corrected_json=extracted, notes=item.get("notes"))
        new_queue = get_work_queue()
        for i, q in enumerate(new_queue):
            q["_index"] = i
        pos = next(
            (i for i, q in enumerate(new_queue) if q["element_id"] == eid), index
        )
        if pos >= len(new_queue):
            pos = 0
        it = new_queue[pos]
        author_text, resources_text, thumb_path = _enrichment_preview(
            it, include_thumbnail=True
        )
        cards, trace_md, raw, _ej, counter, _cv, corr_str, notes = render_item(
            it, False, len(new_queue), pos, author_text, resources_text
        )
        return (
            {"queue": new_queue, "index": pos},
            cards,
            trace_md,
            raw,
            counter,
            corr_str,
            notes,
            "Marked incorrect. Edit correction below.",
            author_text,
            resources_text,
            thumb_path,
        )

    def on_save_correction(state, corrected_json_str, notes):
        queue, index = _get_queue_index(state)
        if not queue or index >= len(queue):
            return "No item.", ""
        item = queue[index]
        eid = item["element_id"]
        try:
            corrected = (
                json.loads(corrected_json_str) if corrected_json_str.strip() else None
            )
        except json.JSONDecodeError:
            return "Invalid JSON.", ""
        update_correction(eid, corrected_json=corrected, notes=notes or None)
        return "Correction saved.", ""

    def on_mark_fixed(state):
        queue, index = _get_queue_index(state)
        if not queue or index >= len(queue):
            return (
                state,
                "_No items._",
                "",
                {},
                "0 / 0",
                "{}",
                "",
                "No item.",
                "No item.",
                "No item.",
                None,
            )
        item = queue[index]
        eid = item["element_id"]
        update_status(eid, STATUS_FIXED_VALIDATED)
        new_queue = get_work_queue()
        for i, q in enumerate(new_queue):
            q["_index"] = i
        if index >= len(new_queue):
            index = max(0, len(new_queue) - 1)
        if not new_queue:
            return (
                {"queue": [], "index": 0},
                "_No items._",
                "",
                {},
                "0 / 0",
                "{}",
                "",
                "Marked fixed. Queue empty.",
                "No item.",
                "No item.",
                None,
            )
        it = new_queue[index]
        author_text, resources_text, thumb_path = _enrichment_preview(
            it, include_thumbnail=True
        )
        cards, trace_md, raw, _ej, counter, _cv, corr_str, notes = render_item(
            it, False, len(new_queue), index, author_text, resources_text
        )
        return (
            {"queue": new_queue, "index": index},
            cards,
            trace_md,
            raw,
            counter,
            corr_str,
            notes,
            "Marked fixed + validated.",
            author_text,
            resources_text,
            thumb_path,
        )

    def _enrichment_preview(item: dict, include_thumbnail: bool = False) -> tuple:
        """Author and resources from one fetch per URL.
        Thumbnail only when include_thumbnail=True (on-demand)."""
        if not item:
            return "No item.", "No item.", None
        preview = item.get("corrected_json") or item.get("extracted_json") or {}
        raw = item.get("raw_json") or {}
        url = _get_post_url_from_extracted(preview)
        if not url:
            url = _get_post_url_from_raw(raw)
        details = (
            extract_author_profile_with_details(url)
            if url and is_author_enrichment_enabled()
            else {}
        )
        if not url:
            author_text = "URL tried: (none)\nResult: No Post URL in extracted data or raw element."
        elif not is_author_enrichment_enabled():
            author_text = "Author enrichment disabled (ENABLE_AUTHOR_ENRICHMENT=0)."
        else:
            author_text = (
                _format_author_result(details) if details else _format_author_result({})
            )
        content = (details.get("content") or "").strip()
        content_source = "fetched page"
        if not content:
            content = _get_content_from_extracted(preview)
            content_source = "extracted"
        if not content:
            content = _get_content_from_raw(raw)
            content_source = "raw API"
        urls = extract_urls_from_text(content) if content else []
        resources_text = _format_resources_result(content, urls, content_source)
        thumbnail_path = (
            get_thumbnail_path_for_url(url) if (url and include_thumbnail) else None
        )
        return author_text, resources_text, thumbnail_path

    def on_extract_author(state):
        queue, index = _get_queue_index(state)
        if not queue or index >= len(queue):
            return "No item."
        try:
            author_text, _, _ = _enrichment_preview(
                queue[index], include_thumbnail=False
            )
            return author_text
        except Exception as e:
            logger.exception("Extract author failed")
            return f"Error extracting author:\n{type(e).__name__}: {e}"

    def on_extract_resources(state):
        queue, index = _get_queue_index(state)
        if not queue or index >= len(queue):
            return "No item."
        try:
            _, resources_text, _ = _enrichment_preview(
                queue[index], include_thumbnail=False
            )
            return resources_text
        except Exception as e:
            logger.exception("Extract resources failed")
            return f"Error extracting resources:\n{type(e).__name__}: {e}"

    def on_regenerate_thumbnail(state):
        """Regenerate thumbnail by deleting cached PNG and regenerating."""
        queue, index = _get_queue_index(state)
        if not queue or index >= len(queue):
            return None
        try:
            item = queue[index]
            preview = item.get("corrected_json") or item.get("extracted_json") or {}
            raw = item.get("raw_json") or {}
            url = _get_post_url_from_extracted(preview)
            if not url:
                url = _get_post_url_from_raw(raw)
            if not url:
                return None
            # Delete cached thumbnail to force regeneration
            from linkedin_api.enrich_profiles import (
                _url_to_cache_key,
                _post_html_cache_dir,
            )

            cache_dir = _post_html_cache_dir()
            if cache_dir:
                cache_key = _url_to_cache_key(url)
                png_path = cache_dir / f"{cache_key}.png"
                if png_path.exists():
                    png_path.unlink()
            # Regenerate
            return get_thumbnail_path_for_url(url)
        except Exception:
            logger.exception("Regenerate thumbnail failed")
            return None

    def on_extract_comment_author(state, comment_author_state):
        """Fetch post HTML, find comment by text, extract author. Store in comment_author_state."""
        queue, index = _get_queue_index(state)
        if not queue or index >= len(queue):
            return None, "No item."
        item = queue[index]
        preview = item.get("corrected_json") or item.get("extracted_json") or {}
        if preview.get("primary") != "comment":
            return (
                comment_author_state,
                "Current item is not a comment (primary \u2260 comment).",
            )
        comment_node = _get_comment_node_from_preview(preview)
        if not comment_node:
            return comment_author_state, "No Comment node with url in extracted data."
        comment_urn, url, text = comment_node
        post_url = _normalize_post_url(url)
        if not post_url:
            return comment_author_state, "Could not normalize comment URL to post URL."
        result = fetch_post_page(post_url, use_cache=True, save_to_cache=True)
        if result.get("error") or result.get("skip_reason"):
            return (
                comment_author_state,
                f"Fetch failed: {result.get('error') or result.get('skip_reason')}",
            )
        html = result.get("html")
        if not html:
            return comment_author_state, "No HTML returned."
        author = parse_comment_author_from_html(html, text)
        if not author:
            return comment_author_state, "Could not find comment author in post HTML."
        current = None
        for r in preview.get("relationships", []):
            if r.get("type") == "CREATES" and r.get("to") == comment_urn:
                current = r.get("from")
                break
        msg = f"**Extracted author:** {author.get('name')} \u2014 {author.get('profile_url')}\n\n"
        if current:
            msg += f"Current CREATES from: `{current}`. Click **Apply comment author to correction** to replace."
        else:
            msg += "No existing author link. Click **Apply comment author to correction** to add."
        new_state = {
            "author_info": author,
            "comment_urn": comment_urn,
            "element_id": item["element_id"],
        }
        return new_state, msg

    def _apply_comment_author_no_op(state, msg, corrected_json_str, notes):
        """Build 12-tuple for apply_comment_author when we don't actually apply."""
        queue, index = _get_queue_index(state)
        if not queue or index >= len(queue):
            return (
                state,
                msg,
                "{}",
                "_No items._",
                "",
                {},
                "0 / 0",
                "",
                "No item.",
                "No item.",
                None,
                None,
            )
        item = queue[index]
        author_text, resources_text, thumb_path = _enrichment_preview(
            item, include_thumbnail=True
        )
        cards, trace_md, raw, _ej, counter, _cv, corr_str, notes_out = render_item(
            item, False, len(queue), index, author_text, resources_text
        )
        return (
            state,
            msg,
            corrected_json_str or corr_str,
            cards,
            trace_md,
            raw,
            counter,
            notes or notes_out,
            author_text,
            resources_text,
            thumb_path,
            None,
        )

    def on_apply_comment_author(state, corrected_json_str, notes, comment_author_state):
        """Apply stored comment author to correction and save."""
        if not comment_author_state or not isinstance(comment_author_state, dict):
            return _apply_comment_author_no_op(
                state,
                "No extracted comment author. Click **Extract comment author from post** first.",
                corrected_json_str,
                notes,
            )
        queue, index = _get_queue_index(state)
        if not queue or index >= len(queue):
            return _apply_comment_author_no_op(
                state, "No item.", corrected_json_str, notes
            )
        item = queue[index]
        if item.get("element_id") != comment_author_state.get("element_id"):
            return _apply_comment_author_no_op(
                state,
                "Item changed. Extract comment author again for the current item.",
                corrected_json_str,
                notes,
            )
        eid = item["element_id"]
        author_info = comment_author_state.get("author_info")
        comment_urn = comment_author_state.get("comment_urn")
        if not author_info or not comment_urn:
            return _apply_comment_author_no_op(
                state, "Invalid stored state.", corrected_json_str, notes
            )
        try:
            payload = (
                json.loads(corrected_json_str)
                if corrected_json_str.strip()
                else item.get("extracted_json", {})
            )
        except json.JSONDecodeError:
            return _apply_comment_author_no_op(
                state, "Invalid correction JSON.", corrected_json_str, notes
            )
        new_payload = _apply_comment_author_to_payload(
            payload, comment_urn, author_info
        )
        update_correction(
            eid, corrected_json=new_payload, notes=notes or item.get("notes")
        )
        fresh = get_item(eid)
        if fresh and queue:
            new_queue = list(queue)
            new_queue[index] = fresh
            state = {**state, "queue": new_queue, "index": index}
        author_text, resources_text, thumb_path = _enrichment_preview(
            fresh or item, include_thumbnail=True
        )
        cards, trace_md, raw, _ej, counter, _cv, corr_str, notes_out = render_item(
            fresh or item, False, len(queue), index, author_text, resources_text
        )
        return (
            state,
            "Comment author applied to correction.",
            json.dumps(new_payload, indent=2, default=str),
            cards,
            trace_md,
            raw,
            counter,
            notes or notes_out,
            author_text,
            resources_text,
            thumb_path,
            None,
        )

    def on_export_fixtures():
        n = export_fixtures()
        return f"Exported {n} fixture(s) to outputs/review/fixtures/"

    def on_toggle_json(show_json, state):
        queue, index = _get_queue_index(state)
        if not queue or index >= len(queue):
            return "_No items._"
        item = queue[index]
        preview = item.get("corrected_json") or item.get("extracted_json") or {}
        if show_json:
            return (
                "**Extracted (JSON)**\n\n```json\n"
                + json.dumps(preview, indent=2, default=str)
                + "\n```"
            )
        return _extracted_to_markdown_cards(preview)

    with gr.Blocks(title="LinkedIn Extraction Review", theme=gr.themes.Soft()) as demo:
        review_state = gr.State(value=_review_state_default())
        comment_author_state = gr.State(value=None)
        gr.Markdown(
            "# LinkedIn Extraction Review\n"
            "Review Portability API extraction item-by-item. Load data, then use "
            "the queue to validate, skip, or correct.\n\n"
            "*To stop the app: press **Ctrl+C** in the terminal.*"
        )

        with gr.Row():
            start_time_in = gr.Textbox(
                label="Start time (epoch ms, optional)",
                placeholder="Leave empty for .last_run, or 0 to fetch from beginning",
            )
            load_btn = gr.Button("Load from API and sync", variant="primary")
        load_status = gr.Markdown(
            value="Click Load to fetch changelog and build work queue (pending + needs_fix + skipped)."
        )

        gr.Markdown("---")
        gr.Markdown("### Current item")

        with gr.Row():
            with gr.Column(scale=2):
                cards_out = gr.Markdown(label="Extracted (property cards)")
                show_json_toggle = gr.Checkbox(label="Show extracted JSON", value=False)
                trace_out = gr.Markdown(label="Trace (field ← json_path)")
            with gr.Column(scale=1):
                raw_json_out = gr.JSON(label="Raw element JSON")
                gr.Markdown(
                    "*For reaction/comment elements the raw changelog does not "
                    "include the post body (only the post URN); post content "
                    "appears only for post elements.*",
                    elem_classes=["small"],
                )
            with gr.Column(scale=1):
                thumbnail_out = gr.Image(
                    label="Post preview", type="filepath", height=300, show_label=False
                )
                regenerate_thumb_btn = gr.Button("Regenerate thumbnail", size="sm")

        counter_out = gr.Markdown(value="0 / 0")
        with gr.Row():
            prev_btn = gr.Button("Previous")
            next_btn = gr.Button("Next")
            validate_btn = gr.Button("Validate", variant="primary")
            skip_btn = gr.Button("Skip")
            incorrect_btn = gr.Button("Incorrect (needs fix)")

        with gr.Accordion("Correction editor (when status = needs_fix)", open=True):
            corrected_json_in = gr.Textbox(
                label="Corrected extraction (JSON)", lines=12
            )
            notes_in = gr.Textbox(label="Notes")
            with gr.Row():
                save_correction_btn = gr.Button("Save correction")
                mark_fixed_btn = gr.Button("Mark fixed + validated")
        correction_status = gr.Markdown(visible=False)

        with gr.Accordion("Enrichment preview", open=True):
            with gr.Row():
                with gr.Column(scale=1):
                    extract_author_btn = gr.Button("Extract author (from post URL)")
                    author_out = gr.Textbox(label="Author", lines=3)
                    extract_resources_btn = gr.Button(
                        "Extract resources (URLs from content)"
                    )
                    resources_out = gr.Textbox(label="URLs", lines=5)
                with gr.Column(scale=1):
                    extract_comment_author_btn = gr.Button(
                        "Extract comment author from post"
                    )
                    apply_comment_author_btn = gr.Button(
                        "Apply comment author to correction"
                    )

        export_btn = gr.Button("Export fixtures")
        export_status = gr.Markdown(value="")

        action_msg = gr.Markdown(value="")

        load_btn.click(
            fn=on_load,
            inputs=[start_time_in],
            outputs=[
                review_state,
                load_status,
                cards_out,
                trace_out,
                raw_json_out,
                counter_out,
                corrected_json_in,
                notes_in,
                action_msg,
                author_out,
                resources_out,
                thumbnail_out,
            ],
        )

        prev_btn.click(
            fn=on_prev,
            inputs=[review_state],
            outputs=[
                review_state,
                cards_out,
                trace_out,
                raw_json_out,
                counter_out,
                corrected_json_in,
                notes_in,
                author_out,
                resources_out,
                thumbnail_out,
            ],
        )

        next_btn.click(
            fn=on_next,
            inputs=[review_state],
            outputs=[
                review_state,
                cards_out,
                trace_out,
                raw_json_out,
                counter_out,
                corrected_json_in,
                notes_in,
                author_out,
                resources_out,
                thumbnail_out,
            ],
        )

        validate_btn.click(
            fn=on_validate,
            inputs=[review_state],
            outputs=[
                review_state,
                cards_out,
                trace_out,
                raw_json_out,
                counter_out,
                corrected_json_in,
                notes_in,
                action_msg,
                author_out,
                resources_out,
                thumbnail_out,
            ],
        )

        skip_btn.click(
            fn=on_skip,
            inputs=[review_state],
            outputs=[
                review_state,
                cards_out,
                trace_out,
                raw_json_out,
                counter_out,
                corrected_json_in,
                notes_in,
                action_msg,
                author_out,
                resources_out,
                thumbnail_out,
            ],
        )

        incorrect_btn.click(
            fn=on_incorrect,
            inputs=[review_state],
            outputs=[
                review_state,
                cards_out,
                trace_out,
                raw_json_out,
                counter_out,
                corrected_json_in,
                notes_in,
                action_msg,
                author_out,
                resources_out,
                thumbnail_out,
            ],
        )

        save_correction_btn.click(
            fn=on_save_correction,
            inputs=[review_state, corrected_json_in, notes_in],
            outputs=[action_msg, correction_status],
        )

        mark_fixed_btn.click(
            fn=on_mark_fixed,
            inputs=[review_state],
            outputs=[
                review_state,
                cards_out,
                trace_out,
                raw_json_out,
                counter_out,
                corrected_json_in,
                notes_in,
                action_msg,
                author_out,
                resources_out,
                thumbnail_out,
            ],
        )

        extract_author_btn.click(
            fn=on_extract_author,
            inputs=[review_state],
            outputs=[author_out],
        )
        extract_resources_btn.click(
            fn=on_extract_resources,
            inputs=[review_state],
            outputs=[resources_out],
        )
        regenerate_thumb_btn.click(
            fn=on_regenerate_thumbnail,
            inputs=[review_state],
            outputs=[thumbnail_out],
        )

        extract_comment_author_btn.click(
            fn=on_extract_comment_author,
            inputs=[review_state, comment_author_state],
            outputs=[comment_author_state, author_out],
        )
        apply_comment_author_btn.click(
            fn=on_apply_comment_author,
            inputs=[review_state, corrected_json_in, notes_in, comment_author_state],
            outputs=[
                review_state,
                action_msg,
                corrected_json_in,
                cards_out,
                trace_out,
                raw_json_out,
                counter_out,
                notes_in,
                author_out,
                resources_out,
                thumbnail_out,
                comment_author_state,
            ],
        )
        export_btn.click(fn=on_export_fixtures, outputs=[export_status])

        show_json_toggle.change(
            fn=on_toggle_json,
            inputs=[show_json_toggle, review_state],
            outputs=[cards_out],
        )

    return demo
