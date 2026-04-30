"""
URL extraction and categorization utilities.

Extracted from extract_resources.py for reuse across modules.
"""

import re
from typing import Dict, List, Optional, Tuple
from urllib.parse import parse_qs, unquote, urlparse


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


def linkedin_signup_redirect_hashtag(url: str) -> Optional[str]:
    """Return the hashtag keyword when a LinkedIn signup/authwall URL wraps a hashtag link.

    LinkedIn serves static HTML where hashtag ``<a>`` tags point to
    ``/signup/cold-join?session_redirect=.../feed/hashtag/<keyword>`` for
    unauthenticated visitors.  This decodes the redirect destination and
    extracts the hashtag keyword so callers can add it to ``tags`` rather
    than treating the signup URL as a fetchable resource.
    """
    if not url or not is_linkedin_internal_url(url):
        return None
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return None
    path = parsed.path.lower()
    if "/signup/" not in path and "/authwall" not in path:
        return None
    try:
        params = parse_qs(parsed.query)
        redirect = (params.get("session_redirect") or [""])[0]
    except Exception:
        return None
    if not redirect:
        return None
    return linkedin_hashtag_keyword(unquote(redirect))


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
    urls: List[str],
) -> Tuple[List[str], List[Dict[str, str]], List[str]]:
    """
    Classify a list of URLs for content-store metadata.

    Returns ``(urls, mentions, tags)``:

    - ``urls`` — resources and other links, excluding hashtag and profile/company/school URLs.
    - ``mentions`` — ``{"name": str, "url": str}`` for LinkedIn profiles/companies/schools.
    - ``tags`` — hashtag keywords only (no URL stored), from ``/feed/hashtag/…`` links.
    """
    deduped = list(dict.fromkeys(u.strip() for u in (urls or []) if u and u.strip()))
    tags_set: set[str] = set()
    mentions_map: Dict[str, Dict[str, str]] = {}
    resource_urls: List[str] = []

    for u in deduped:
        hk = linkedin_hashtag_keyword(u) or linkedin_signup_redirect_hashtag(u)
        if hk:
            tags_set.add(hk)
            continue
        if is_linkedin_mention_url(u):
            mentions_map[u] = {"name": "", "url": u}
            continue
        if should_ignore_url(u):
            continue
        resource_urls.append(u)

    return resource_urls, list(mentions_map.values()), sorted(tags_set)


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
    """Check if URL should be ignored (hashtags, profile links, auth pages, etc.)."""
    if "linkedin.com/in/" in url or "linkedin.com/pub/" in url:
        return True
    if "linkedin.com/feed/hashtag/" in url:
        return True
    if "linkedin.com/company/" in url:
        return True
    if url.startswith("https://www.linkedin.com/feed/"):
        return True
    if "linkedin.com/signup/" in url or "linkedin.com/authwall" in url:
        return True
    if "linkedin.com/showcase/" in url or "linkedin.com/school/" in url:
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
            url, timeout=(5, 10), allow_redirects=True, headers=headers, verify=verify
        )
        if response.url != url:
            return str(response.url)
    except Exception:
        pass

    return url
