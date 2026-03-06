"""
URL extraction and categorization utilities.

Extracted from extract_resources.py for reuse across modules.
"""

import re
from typing import Dict, List, Optional
from urllib.parse import urlparse


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
            # LinkedIn shows a security interstitial with the target URL in
            # the page text: "This link will take you to… https://…"
            # Parsing with BeautifulSoup and searching get_text() naturally
            # excludes URLs buried in HTML attributes (script src, link href…).
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, "html.parser")
                for found in re.findall(r"https?://\S+", soup.get_text()):
                    found = found.rstrip(".,;:!?)")
                    if (
                        "linkedin.com" not in found.lower()
                        and "lnkd.in" not in found.lower()
                    ):
                        return found
            # Direct redirect (no interstitial): lnkd.in → target. Use final URL
            # even if target returns 406, 404, etc. (e.g. GitHub 406, expired lnkd.in).
            if response.url and response.url != url:
                final = response.url
                if (
                    "linkedin.com" not in final.lower()
                    and "lnkd.in" not in final.lower()
                ):
                    return final
        except Exception:
            pass
        return url

    try:
        response = requests.head(
            url, timeout=15, allow_redirects=True, headers=headers, verify=verify
        )
        if response.url != url:
            return response.url
    except Exception:
        pass

    return url
