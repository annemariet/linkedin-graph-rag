"""
URL extraction and categorization utilities.

Extracted from extract_resources.py for reuse across modules.
"""

import re
from typing import Dict, List, Optional, Tuple
from urllib.parse import unquote, urlparse


_MARKDOWN_LINK_URL = re.compile(r"\]\((https?://[^)]+)\)")
_MARKDOWN_LINK_LABEL = re.compile(r"\[([^\]]*)\]\((https?://[^)]+)\)")


def extract_urls_from_markdown(text: str) -> List[str]:
    """URLs inside Markdown ``[...](url)`` link targets."""
    if not text:
        return []
    found = _MARKDOWN_LINK_URL.findall(text)
    return list(dict.fromkeys(f.strip() for f in found if f.strip()))


def extract_markdown_links(text: str) -> List[Tuple[str, str]]:
    """``(link_text, url)`` for each ``[text](url)`` in *text* (best-effort)."""
    if not text:
        return []
    out: List[Tuple[str, str]] = []
    for m in _MARKDOWN_LINK_LABEL.finditer(text):
        label = (m.group(1) or "").strip()
        url = (m.group(2) or "").strip()
        if url:
            out.append((label, url))
    return out


def linkedin_hashtag_keyword(url: str) -> Optional[str]:
    """Hashtag text from a LinkedIn hashtag URL, or None if not a hashtag link."""
    if not url or not is_linkedin_internal_url(url):
        return None
    try:
        path = urlparse(url.strip()).path
    except Exception:
        return None
    m = re.search(r"/hashtag/([^/?#]+)", path, re.I)
    if not m:
        return None
    return unquote(m.group(1)).strip() or None


def is_linkedin_mention_url(url: str) -> bool:
    """True for LinkedIn profile, company, or school URLs."""
    if not url or not is_linkedin_internal_url(url):
        return False
    try:
        path = urlparse(url.strip()).path.lower()
    except Exception:
        return False
    return bool(
        re.match(r"/in/[^/]+", path)
        or re.match(r"/company/[^/]+", path)
        or re.match(r"/school/[^/]+", path)
    )


def extract_classified_links(
    body: str,
    extra_urls: Optional[List[str]] = None,
) -> Tuple[List[str], List[Dict[str, str]], List[str]]:
    """
    Classify hyperlinks in post body text for content-store metadata.

    Returns ``(urls, mentions, tags)``:

    - ``urls`` — resources and other links (posts, Pulse, ``/redir/``, external sites,
      ``lnkd.in``, etc.), excluding pure hashtag URLs and profile/company/school links.
    - ``mentions`` — ``{"name": str, "url": str}`` for LinkedIn profiles/companies/schools;
      *name* from markdown label when available.
    - ``tags`` — hashtag keywords only (no URL stored), from ``/feed/hashtag/…`` links.
    """
    extras = list(
        dict.fromkeys(x.strip() for x in (extra_urls or []) if x and x.strip())
    )
    md_pairs = extract_markdown_links(body or "")
    label_by_url: Dict[str, str] = {}
    for label, u in md_pairs:
        if u not in label_by_url:
            label_by_url[u] = label

    from_md = extract_urls_from_markdown(body or "")
    from_plain = extract_urls_from_text(body or "")
    all_urls = list(dict.fromkeys(from_md + from_plain + extras))

    tags_set: set[str] = set()
    mentions_map: Dict[str, Dict[str, str]] = {}
    resource_urls: List[str] = []

    for u in all_urls:
        hk = linkedin_hashtag_keyword(u)
        if hk:
            tags_set.add(hk)
            continue
        if is_linkedin_mention_url(u):
            mentions_map[u] = {
                "name": label_by_url.get(u, ""),
                "url": u,
            }
            continue
        resource_urls.append(u)

    mentions_list = list(mentions_map.values())
    tags_list = sorted(tags_set)
    return resource_urls, mentions_list, tags_list


def extract_urls_from_text(text: str) -> List[str]:
    """
    Extract all URLs from text using regex.

    Args:
        text: Text content to search for URLs

    Returns:
        List of unique URLs found
    """
    if not text:
        return []

    url_pattern = r"https?://[^\s<>\"'{}|\\^`\[\]]+[^\s<>\"'{}|\\^`\[\].,;:!?]"
    urls = re.findall(url_pattern, text)

    cleaned_urls = []
    for url in urls:
        url = url.rstrip(".,;:!?)")
        try:
            parsed = urlparse(url)
            if parsed.netloc:
                cleaned_urls.append(url)
        except Exception:
            continue

    return list(set(cleaned_urls))


def categorize_url(url: str) -> Dict[str, Optional[str]]:
    """
    Categorize a URL by domain and type.

    Returns:
        Dict with 'domain' and 'type' keys
    """
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        path = parsed.path.lower()

        if domain.startswith("www."):
            domain = domain[4:]

        url_lower = url.lower()
        file_extensions = {
            ".pdf": "document",
            ".doc": "document",
            ".docx": "document",
            ".ppt": "presentation",
            ".pptx": "presentation",
            ".mp4": "video",
            ".jpg": "image",
            ".jpeg": "image",
            ".png": "image",
            ".gif": "image",
            ".svg": "image",
        }

        resource_type: Optional[str]
        for ext, resource_type in file_extensions.items():
            if ext in url_lower:
                return {"domain": domain, "type": resource_type}

        resource_type = None

        if any(d in domain for d in ["youtube.com", "youtu.be", "vimeo.com"]):
            resource_type = "video"
        elif any(d in domain for d in ["github.com", "gitlab.com", "bitbucket.org"]):
            resource_type = "repository"
        elif any(d in domain for d in ["docs.", "readthedocs.io"]):
            resource_type = "documentation"
        elif any(
            d in domain
            for d in ["medium.com", "substack.com", "dev.to", "hashnode.com"]
        ) or any(p in path for p in ["/blog/", "/article/"]):
            resource_type = "article"
        elif any(d in domain for d in ["arxiv.org", "scholar.google.com"]):
            resource_type = "research"
        elif "linkedin.com" in domain and "/pulse/" in url:
            resource_type = "article"

        if resource_type is None:
            resource_type = "article"

        return {"domain": domain, "type": resource_type}
    except Exception:
        return {"domain": None, "type": "unknown"}


def is_linkedin_internal_url(url: str) -> bool:
    """True for linkedin.com / lnkd.in hosts (incl. regional subdomains)."""
    if not (url or "").strip():
        return False
    try:
        netloc = urlparse(url.strip()).netloc.lower()
    except Exception:
        return False
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return (
        "linkedin.com" in netloc or netloc == "lnkd.in" or netloc.endswith(".lnkd.in")
    )


def is_comment_feed_url(url: str) -> bool:
    """True if URL is a feed/update with a comment URN (not a post); such URLs don't return post content."""
    return bool(url and "urn:li:comment:" in url)


def should_ignore_url(url: str) -> bool:
    """Check if URL should be ignored (hashtags, profile links, etc.)."""
    if "linkedin.com/in/" in url or "linkedin.com/pub/" in url:
        return True
    if "linkedin.com/feed/hashtag/" in url:
        return True
    if "linkedin.com/company/" in url:
        return True
    if url.startswith("https://www.linkedin.com/feed/"):
        return True
    return False


def resolve_redirect(url: str, max_redirects: int = 5) -> str:
    """Resolve redirects to get the final URL.

    Handles LinkedIn short URLs (lnkd.in) which use an intermediate page.
    When lnkd.in redirects directly (no interstitial), uses response.url even
    if the final server returns 4xx/5xx (e.g. 406).

    Returns:
        Final URL after following redirects, or original URL if resolution fails
    """
    import os

    import requests
    from bs4 import BeautifulSoup

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    verify = os.environ.get("REQUESTS_SSL_VERIFY", "true").lower() not in ("0", "false")

    if "lnkd.in" in url:
        try:
            response = requests.get(
                url, timeout=15, allow_redirects=True, headers=headers, verify=verify
            )
            # Prefer the final non-LinkedIn URL from the HTTP redirect chain when present.
            if response.history:
                for hop in reversed(list(response.history) + [response]):
                    hop_url = str(getattr(hop, "url", ""))
                    hop_lower = hop_url.lower()
                    if (
                        hop_url
                        and "linkedin.com" not in hop_lower
                        and "lnkd.in" not in hop_lower
                    ):
                        return hop_url
            # LinkedIn sometimes shows a security interstitial with the target URL in
            # the page text: "This link will take you to… https://…"
            # Parsing with BeautifulSoup and searching get_text() naturally
            # excludes URLs buried in HTML attributes (script src, link href…).
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, "html.parser")
                for found in re.findall(r"https?://\S+", soup.get_text()):
                    found_str = str(found).rstrip(".,;:!?)")
                    found_lower = found_str.lower()
                    if (
                        "linkedin.com" not in found_lower
                        and "lnkd.in" not in found_lower
                    ):
                        return found_str
            # Direct redirect (no interstitial): lnkd.in → target. Use final URL
            # even if target returns 406, 404, etc. (e.g. GitHub 406, expired lnkd.in).
            if response.url and response.url != url:
                final = str(response.url)
                final_lower = final.lower()
                if "linkedin.com" not in final_lower and "lnkd.in" not in final_lower:
                    return final
        except Exception:
            pass
        return url

    try:
        response = requests.head(
            url, timeout=15, allow_redirects=True, headers=headers, verify=verify
        )
        if response.url != url:
            return str(response.url)
    except Exception:
        pass

    return url
