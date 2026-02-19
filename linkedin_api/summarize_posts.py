#!/usr/bin/env python3
"""
Phase 3: Summarize posts with LLM.

Reads from content store (populated by enrich_activities). Batches posts,
sends to LLM, extracts summary, topics, technologies, people, category.
Output written to metadata sidecar (.meta.json).
"""

from __future__ import annotations

import argparse
import json
import re
import warnings
from pathlib import Path

from linkedin_api.content_store import (
    list_posts_needing_summary,
    save_content,
    save_metadata,
    update_summary_metadata,
)
from linkedin_api.llm_config import create_llm

BATCH_SIZE = 5

_SYSTEM_PROMPT = """You extract structured metadata from LinkedIn posts. For each post provide:
- summary: 1-2 sentence summary
- topics: list of main topics/themes (e.g. ["AI", "careers"])
- technologies: tools, frameworks, languages mentioned (e.g. ["Python", "PyTorch"])
- people: named people or roles mentioned (e.g. ["Jane Doe", "CTO"])
- category: one of product_announcement, paper, experiment, job_news, opinion, tutorial, other.

Example categories you can pick from: product_announcement (new lib/product), paper (academic/research),
  experiment (trial/benchmark), job_news (hiring/career), opinion (hot take),
  tutorial (how-to), other.
Use empty arrays [] for topics/technologies/people when none apply.
Output valid JSON only. Format: {"posts": [{"urn": "...", "summary": "...",
  "topics": [], "technologies": [], "people": [], "category": "..."}]}"""

_USER_PROMPT_TEMPLATE = """For each post below: write a 1-2 sentence summary and fill in
topics, technologies, people, and category as relevant. Output JSON only.

---
{posts}
---
"""


def _truncate(content: str, max_chars: int = 2000) -> str:
    if len(content) <= max_chars:
        return content
    return content[:max_chars] + "\n...[truncated]"


def _build_prompt_batch(posts: list[dict]) -> str:
    parts = []
    for i, p in enumerate(posts, 1):
        urn = p.get("urn", "")
        content = _truncate(p.get("content", ""))
        parts.append(f"[Post {i}]\nURN: {urn}\nContent:\n{content}\n")
    return "\n".join(parts)


def _parse_llm_response(text: str, urns: list[str]) -> list[dict]:
    """Extract JSON from LLM output. urns used to match back to posts."""
    text = text.strip()
    # Try to find JSON block
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return []
    try:
        data = json.loads(match.group())
        posts = data.get("posts", data) if isinstance(data, dict) else data
        if not isinstance(posts, list):
            return []
        result = []
        for i, p in enumerate(posts[: len(urns)]):
            if isinstance(p, dict):
                urn = p.get("urn") or (urns[i] if i < len(urns) else "")
                result.append(
                    {
                        "urn": urn,
                        "summary": str(p.get("summary", "")).strip(),
                        "topics": [str(x) for x in (p.get("topics") or []) if x],
                        "technologies": [
                            str(x) for x in (p.get("technologies") or []) if x
                        ],
                        "people": [str(x) for x in (p.get("people") or []) if x],
                        "category": str(p.get("category", "")).strip() or None,
                    }
                )
        return result
    except json.JSONDecodeError:
        return []


def _summarize_batch(posts: list[dict], llm) -> int:
    """Summarize one batch. Returns count updated."""
    user_prompt = _USER_PROMPT_TEMPLATE.format(posts=_build_prompt_batch(posts))
    prompt = f"{_SYSTEM_PROMPT}\n\n{user_prompt}"
    urns = [p["urn"] for p in posts]
    try:
        response = llm.invoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        parsed = _parse_llm_response(content, urns)
        for p in parsed:
            urn = p["urn"]
            if urn:
                update_summary_metadata(
                    urn,
                    summary=p["summary"],
                    topics=p["topics"],
                    technologies=p["technologies"],
                    people=p["people"],
                    category=p.get("category"),
                )
        return len(parsed)
    except Exception as e:
        print(f"  LLM error: {e}")
        return 0


def load_from_json_and_save(path) -> int:
    """Load enriched activities JSON, upsert into content store. Returns count saved."""
    data = json.loads(path.read_text())
    activities = data if isinstance(data, list) else data.get("activities", [])
    seen: set[str] = set()
    count = 0
    for a in activities:
        urn = a.get("post_urn", "")
        content = a.get("content", "")
        urls = a.get("urls") or []
        post_url = a.get("post_url", "")
        if not urn or not content or len(content) < 50 or urn in seen:
            continue
        seen.add(urn)
        save_content(urn, content)
        save_metadata(urn, urls=urls, post_url=post_url or "")
        count += 1
    return count


def summarize_posts(
    *,
    from_json: str | None = None,
    limit: int | None = None,
    batch_size: int = BATCH_SIZE,
    quiet: bool = False,
) -> int:
    """Summarize posts. Returns count summarized."""
    if from_json:
        p = Path(from_json)
        if p.exists():
            n = load_from_json_and_save(p)
            if not quiet:
                print(f"Loaded {n} posts from {from_json} into store")
    posts = list_posts_needing_summary(limit=limit)
    if not posts:
        if not quiet:
            print("No posts needing summary.")
        return 0
    from tqdm import tqdm

    llm = create_llm(quiet=quiet)
    total = 0
    batches = [posts[i : i + batch_size] for i in range(0, len(posts), batch_size)]
    it = tqdm(batches, desc="Summarize", unit="batch", disable=quiet)
    for batch in it:
        n = _summarize_batch(batch, llm)
        total += n
        it.set_postfix(done=total)
    if total == 0 and not quiet:
        warnings.warn(
            "No posts were summarized (LLM errors?). Check LLM_MODEL and API key."
        )
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize posts via LLM (Phase 3).")
    parser.add_argument(
        "--from-json",
        type=str,
        metavar="PATH",
        help="Load enriched activities JSON into store first",
    )
    parser.add_argument("--limit", type=int, help="Max posts to process")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    parser.add_argument("-q", "--quiet", action="store_true")
    args = parser.parse_args()
    n = summarize_posts(
        from_json=args.from_json,
        limit=args.limit,
        batch_size=args.batch_size,
        quiet=args.quiet,
    )
    if not args.quiet:
        if n == 0:
            print("Summarized 0 posts.")
        else:
            print(f"Summarized {n} posts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
