"""Extract post author and timestamps from public LinkedIn post HTML."""

from __future__ import annotations

import json
import re
from typing import Any

from bs4 import BeautifulSoup

_LI_SUBDOMAIN = re.compile(r"https?://[a-z]{2}\.linkedin\.com", re.I)

# Same as enrich_activities / enrich_profiles (public post body)
_CONTENT_SELECTORS = [
    "article[data-id]",
    ".feed-shared-update-v2__description",
    ".feed-shared-text",
    '[data-test-id="main-feed-activity-card"]',
]


def normalize_linkedin_profile_url(url: str) -> str:
    """Normalize regional linkedin.com hosts to https://www.linkedin.com."""
    s = (url or "").strip()
    if not s:
        return ""
    s = s.split("?")[0]
    s = _LI_SUBDOMAIN.sub("https://www.linkedin.com", s)
    if s.startswith("//linkedin.com"):
        s = "https://www.linkedin.com" + s[len("//linkedin.com") :]
    elif "//linkedin.com" in s and not s.startswith("https://www.linkedin.com"):
        s = s.replace("//linkedin.com", "//www.linkedin.com", 1)
        if s.startswith("//www.linkedin.com"):
            s = "https:" + s
    return s


def _author_from_json_ld_node(obj: dict[str, Any]) -> dict[str, str]:
    """Pull post author and date from a schema.org SocialMediaPosting-like node."""
    out: dict[str, str] = {}
    t = obj.get("@type")
    types = {t} if isinstance(t, str) else set(t or [])
    if not types & {"SocialMediaPosting", "Article", "NewsArticle", "BlogPosting"}:
        return out

    dp = obj.get("datePublished")
    if dp:
        out["post_created_at"] = str(dp).strip()

    author = obj.get("author")
    if isinstance(author, list):
        author = next((x for x in author if isinstance(x, dict)), None)
    if not isinstance(author, dict):
        return out

    name = (author.get("name") or "").strip()
    url = (author.get("url") or "").strip()
    if name and 1 < len(name) < 200:
        out["post_author"] = name
    if url:
        nu = normalize_linkedin_profile_url(url)
        if nu:
            out["post_author_url"] = nu
    return out


def _iter_ld_json_objects(soup: BeautifulSoup):
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text() or ""
        raw = raw.strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    yield item
        elif isinstance(data, dict):
            yield data


def parse_post_meta_from_soup(soup: BeautifulSoup) -> dict[str, str]:
    """
    Post author, author URL, and ``post_created_at`` (ISO) from public post HTML.

    Order: JSON-LD ``datePublished`` / ``author``; then ``<meta>`` article times;
    author DOM links last (same as ``parse_post_author_from_soup`` without meta
    key overlap for date).
    """
    merged = parse_post_author_from_soup(soup)
    if not merged.get("post_created_at"):
        for tag in soup.find_all("meta"):
            prop = tag.get("property") or tag.get("name", "")
            content = str(tag.get("content") or "").strip()
            if not content:
                continue
            if prop in ("article:published_time", "og:article:published_time"):
                merged["post_created_at"] = content
                break
    return merged


def parse_post_author_from_soup(soup: BeautifulSoup) -> dict[str, str]:
    """
    Best-effort post author, profile URL, and published time from public post HTML.

    Prefer JSON-LD (``SocialMediaPosting`` / ``Article``) when present; fall back to
    the main feed actor link (``public_post_feed-actor-name`` / ``feed-actor-name``),
    excluding comment actor links.
    """
    merged: dict[str, str] = {}

    for obj in _iter_ld_json_objects(soup):
        part = _author_from_json_ld_node(obj)
        if part.get("post_author") or part.get("post_author_url"):
            merged.update(part)
            break

    if merged.get("post_author") and merged.get("post_author_url"):
        return merged

    for a in soup.find_all("a", href=True):
        href = str(a.get("href") or "")
        if "public_post_comment_" in href:
            continue
        if not (
            "public_post_feed-actor-name" in href or "feed-actor-name" in href
        ) or not ("/in/" in href or "/company/" in href):
            continue
        name = a.get_text(strip=True)
        if not name or not (1 < len(name) < 200):
            continue
        url = normalize_linkedin_profile_url(href)
        if not merged.get("post_author"):
            merged["post_author"] = name
        if not merged.get("post_author_url") and url:
            merged["post_author_url"] = url
        break

    return merged


def parse_post_author_from_html(html: str) -> dict[str, str]:
    if not html:
        return {}
    return parse_post_author_from_soup(BeautifulSoup(html, "html.parser"))


def parse_post_body_from_soup(soup: BeautifulSoup) -> str:
    """Extract main post body text from public LinkedIn HTML."""
    content_text: list[str] = []
    for selector in _CONTENT_SELECTORS:
        for elem in soup.select(selector):
            text = elem.get_text(strip=True)
            if text and len(text) > 20:
                content_text.append(text)
    if content_text:
        return "\n".join(content_text)
    og = soup.find("meta", property="og:description")
    if og and og.get("content"):
        content_text.append(str(og["content"]))
    title = soup.find("title")
    if title:
        t = title.get_text(strip=True)
        if " | " in t:
            content_text.append(t.split(" | ")[0])
    return "\n".join(content_text) if content_text else ""


def parse_post_body_from_html(html: str) -> str:
    if not html:
        return ""
    return parse_post_body_from_soup(BeautifulSoup(html, "html.parser"))


def parse_post_meta_from_html(html: str) -> dict[str, str]:
    """Author, author URL, and ``post_created_at`` from full HTML document."""
    if not html:
        return {}
    soup = BeautifulSoup(html, "html.parser")
    return parse_post_meta_from_soup(soup)
