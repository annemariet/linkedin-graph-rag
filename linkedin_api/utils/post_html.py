"""Extract post author and timestamps from public LinkedIn post HTML."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from bs4.element import NavigableString, PageElement, Tag

_LI_SUBDOMAIN = re.compile(r"https?://[a-z]{2}\.linkedin\.com", re.I)

# Logged-out ``/feed/update/urn:li:activity:…`` often redirects here; og:description is this blurb.
_LI_GENERIC_OG_BLURB = "500 million+ members"
_LI_GENERIC_OG_BLURB_2 = "manage your professional identity"

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


def linkedin_http_fetch_is_blocked(final_url: str, html: str) -> bool:
    """
    True if the HTTP response is LinkedIn's login/signup shell, not a public post page.

    Unauthenticated requests to ``/feed/update/urn:li:…`` commonly redirect to
    ``/signup/cold-join``; parsing ``og:description`` then yields generic marketing
    copy that must not be stored as post content.
    """
    u = (final_url or "").lower()
    if "linkedin.com/signup" in u or "linkedin.com/uas/login" in u:
        return True
    h = html or ""
    if "d_registration-cold-join" in h:
        return True
    if 'data-app-id="com.linkedin.registration-frontend' in h:
        return True
    hl = h.lower()
    if _LI_GENERIC_OG_BLURB.lower() in hl and _LI_GENERIC_OG_BLURB_2.lower() in hl:
        if "socialmediaposting" not in hl:
            return True
    return False


def _find_post_body_element(soup: BeautifulSoup) -> Tag | None:
    """First substantial post body node from known LinkedIn selectors."""
    for selector in _CONTENT_SELECTORS:
        for elem in soup.select(selector):
            text = elem.get_text(strip=True)
            if text and len(text) > 20:
                return elem
    return None


def find_post_body_root(soup: BeautifulSoup) -> Tag | None:
    """Public alias for link classification and DOM-scoped extraction."""
    return _find_post_body_element(soup)


def _collapse_blank_lines(text: str) -> str:
    out = re.sub(r"\n{3,}", "\n\n", text)
    return out.strip()


def _html_inline_to_markdown(node: PageElement, base_url: str) -> str:
    """Convert inline HTML to Markdown (links, emphasis); used inside block walk."""
    if isinstance(node, NavigableString):
        return str(node)
    if not isinstance(node, Tag):
        return ""
    name = node.name.lower()
    if name == "a":
        raw_href = node.get("href")
        if raw_href:
            href = str(raw_href).strip()
            if href.startswith("#") or href.lower().startswith("javascript:"):
                return "".join(
                    _html_inline_to_markdown(c, base_url) for c in node.children
                )
            url = urljoin(base_url, href)
            label = "".join(
                _html_inline_to_markdown(c, base_url) for c in node.children
            )
            label = label.strip() or url
            safe = label.replace("]", "\\]")
            return f"[{safe}]({url})"
        return "".join(_html_inline_to_markdown(c, base_url) for c in node.children)
    if name == "br":
        return "\n"
    if name in ("strong", "b"):
        inner = "".join(_html_inline_to_markdown(c, base_url) for c in node.children)
        return f"**{inner.strip()}**" if inner.strip() else ""
    if name in ("em", "i"):
        inner = "".join(_html_inline_to_markdown(c, base_url) for c in node.children)
        return f"*{inner.strip()}*" if inner.strip() else ""
    if name == "br":
        return "\n"
    return "".join(_html_inline_to_markdown(c, base_url) for c in node.children)


def _html_block_to_markdown(node: PageElement, base_url: str) -> str:
    """Block-level HTML to Markdown paragraphs and lists."""
    if isinstance(node, NavigableString):
        s = str(node)
        return (s + "\n\n") if s.strip() else ""
    if not isinstance(node, Tag):
        return ""
    name = node.name.lower()
    if name in ("script", "style", "noscript"):
        return ""
    if name in ("ul", "ol"):
        items: list[str] = []
        for li in node.find_all("li", recursive=False):
            line = "".join(_html_inline_to_markdown(c, base_url) for c in li.children)
            line = line.strip()
            if line:
                items.append(f"- {line}")
        return ("\n".join(items) + "\n\n") if items else ""
    if name == "li":
        inner = "".join(_html_inline_to_markdown(c, base_url) for c in node.children)
        inner = inner.strip()
        return f"- {inner}\n" if inner else ""
    if name in ("p", "div", "blockquote", "section", "span"):
        inner = "".join(_html_inline_to_markdown(c, base_url) for c in node.children)
        inner = inner.strip()
        return (inner + "\n\n") if inner else ""
    if name in ("h1", "h2", "h3", "h4"):
        inner = "".join(_html_inline_to_markdown(c, base_url) for c in node.children)
        inner = inner.strip()
        level = min(int(name[1]), 4)
        return ("#" * level + " " + inner + "\n\n") if inner else ""
    return "".join(_html_block_to_markdown(c, base_url) for c in node.children)


def _article_to_markdown(root: Tag, base_url: str) -> str:
    """Walk a post root: block tags recurse; unknown tags flatten to inline."""
    parts: list[str] = []
    for child in root.children:
        if isinstance(child, NavigableString):
            s = str(child)
            if s.strip():
                parts.append(s)
            continue
        if not isinstance(child, Tag):
            continue
        cn = child.name.lower()
        if cn in (
            "p",
            "div",
            "blockquote",
            "section",
            "ul",
            "ol",
            "h1",
            "h2",
            "h3",
            "h4",
            "span",
        ):
            parts.append(_html_block_to_markdown(child, base_url))
        elif cn in ("script", "style", "noscript"):
            continue
        elif cn == "br":
            parts.append("\n")
        else:
            parts.append(_html_inline_to_markdown(child, base_url))
    return _collapse_blank_lines("".join(parts))


def parse_post_body_markdown_from_soup(soup: BeautifulSoup, base_url: str = "") -> str:
    """
    Extract post body as Markdown: ``[label](url)`` for anchors (incl. LinkedIn
    profile/hashtag links). Falls back to empty string when no DOM body is found.
    """
    root = _find_post_body_element(soup)
    if root is None:
        return ""
    base = (base_url or "").strip() or "https://www.linkedin.com"
    return _article_to_markdown(root, base)


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
