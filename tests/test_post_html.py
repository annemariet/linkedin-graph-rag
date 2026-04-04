"""Tests for public LinkedIn post HTML parsing (author, JSON-LD, DOM)."""

import os

import pytest
import requests
from bs4 import BeautifulSoup

from linkedin_api.utils.post_html import (
    linkedin_http_fetch_is_blocked,
    normalize_linkedin_profile_url,
    parse_post_author_from_html,
    parse_post_author_from_soup,
    parse_post_meta_from_html,
)

# Shape from a real public post (LUC-65 example); JSON-LD is stable on /posts/ pages.
_SCOTT_CONDRON_JSON_LD = (
    '<script type="application/ld+json">'
    '{"@context":"http://schema.org","@type":"SocialMediaPosting",'
    '"datePublished":"2026-03-10T21:24:58.293Z",'
    '"author":{"name":"Scott Condron","url":"https://ie.linkedin.com/in/condronscott",'
    '"@type":"Person"}}'
    "</script>"
)

_DOM_ONLY_HTML = """
<html><body>
<article data-id="x">
<p class="feed-shared-text">This is the main post body text with enough characters
to pass enrichment length checks here.</p>
</article>
<a href="https://www.linkedin.com/in/example-author?trk=public_post_feed-actor-name">
Jane Example</a>
</body></html>
"""


def test_linkedin_http_fetch_is_blocked_cold_join():
    url = "https://www.linkedin.com/signup/cold-join?session_redirect=x"
    html = '<meta name="pageKey" content="d_registration-cold-join">'
    assert linkedin_http_fetch_is_blocked(url, html) is True


def test_linkedin_http_fetch_is_blocked_generic_og_without_post():
    url = "https://www.linkedin.com/feed/update/urn:li:activity:1"
    html = (
        '<meta property="og:description" content="500 million+ members | '
        "Manage your professional identity. Build and engage with your professional network."
        ' Access knowledge, insights and opportunities.">'
    )
    assert linkedin_http_fetch_is_blocked(url, html) is True


def test_linkedin_http_fetch_not_blocked_real_post_has_jsonld():
    html = (
        '<script type="application/ld+json">'
        '{"@type":"SocialMediaPosting","author":{"name":"A"}}'
        "</script>"
        '<meta property="og:description" content="500 million+ members | Manage your '
        'professional identity. Build and engage with your professional network.">'
    )
    assert (
        linkedin_http_fetch_is_blocked("https://www.linkedin.com/posts/x", html)
        is False
    )


def test_normalize_linkedin_profile_url():
    assert normalize_linkedin_profile_url(
        "https://ie.linkedin.com/in/condronscott?trk=x"
    ) == ("https://www.linkedin.com/in/condronscott")


def test_parse_post_author_from_json_ld_condron_example():
    html = f"<html><head>{_SCOTT_CONDRON_JSON_LD}</head><body></body></html>"
    meta = parse_post_author_from_html(html)
    assert meta["post_author"] == "Scott Condron"
    assert meta["post_author_url"] == "https://www.linkedin.com/in/condronscott"


def test_parse_post_meta_includes_date_from_json_ld():
    html = f"<html><head>{_SCOTT_CONDRON_JSON_LD}</head><body></body></html>"
    meta = parse_post_meta_from_html(html)
    assert meta["post_created_at"] == "2026-03-10T21:24:58.293Z"
    assert meta["post_author"] == "Scott Condron"


def test_parse_post_author_dom_fallback_feed_actor_name():
    soup = BeautifulSoup(_DOM_ONLY_HTML, "html.parser")
    meta = parse_post_author_from_soup(soup)
    assert meta["post_author"] == "Jane Example"
    assert "linkedin.com/in/example-author" in meta["post_author_url"]


def test_parse_post_author_skips_comment_actor_links():
    html = """
    <html><body>
    <a class="comment__author"
       href="https://www.linkedin.com/in/commenter?trk=public_post_comment_actor-name">
       Commenter</a>
    <a href="https://www.linkedin.com/in/poster?trk=public_post_feed-actor-name">
       Real Poster</a>
    </body></html>
    """
    meta = parse_post_author_from_html(html)
    assert meta["post_author"] == "Real Poster"


@pytest.mark.integration
def test_online_public_post_extracts_author_condronscott():
    url = (
        "https://www.linkedin.com/posts/condronscott_github-sakanaaishinkaevolve-"
        "shinkaevolve-activity-7437247151593857024-lWlx"
    )
    if os.getenv("LINKEDIN_TEST_ONLINE") != "1":
        pytest.skip("Set LINKEDIN_TEST_ONLINE=1 to fetch real LinkedIn HTML.")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
    }
    r = requests.get(url, timeout=20, allow_redirects=True, headers=headers)
    assert r.status_code == 200, r.status_code
    meta = parse_post_meta_from_html(r.text)
    assert meta.get("post_author") == "Scott Condron", meta
    assert meta.get("post_author_url"), meta
    assert "condronscott" in meta["post_author_url"].lower()
    assert meta.get("post_created_at"), meta
