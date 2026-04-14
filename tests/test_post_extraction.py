"""Tests for linkedin_api.post_extraction."""

from bs4 import BeautifulSoup

from linkedin_api.post_extraction import (
    _strip_trafilatura_comments,
    classify_links_from_soup,
    merge_classification_with_api,
)


def test_classify_links_skips_comment_trk():
    html = """
    <html><body>
    <article data-id="x">
    <p class="feed-shared-text">Hello this is a longer post body text for the selector
    <a href="https://www.linkedin.com/in/jane?trk=public_post_feed-actor-name">Jane</a>
    <a href="https://www.linkedin.com/in/bob?trk=public_post_comment_actor-name">Bob</a>
    <a href="https://example.com/x">Article</a>
    </p>
    </article>
    </body></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    urls, mentions, tags, _imgs = classify_links_from_soup(
        soup, "https://www.linkedin.com/posts/x"
    )
    assert "https://example.com/x" in urls
    assert any("/in/jane" in m["url"] for m in mentions)
    assert not any("bob" in m["url"].lower() for m in mentions)


def test_merge_classification_prefers_dom_for_mentions():
    dom_u = ["https://github.com/a"]
    dom_m = [{"name": "X", "url": "https://www.linkedin.com/in/x"}]
    u, m, t = merge_classification_with_api(dom_u, dom_m, [], ["https://b.org"])
    assert "https://b.org" in u
    assert any("linkedin.com/in/x" in x["url"] for x in m)


# --- image extraction from JSON-LD ---

_POST_WITH_LD_JSON_IMAGES = """
<html><head>
<script type="application/ld+json">
{"@context":"http://schema.org","@type":"SocialMediaPosting",
 "articleBody":"Post body text here which is long enough to pass",
 "commentCount":3,
 "image":[
   {"url":"https://media.licdn.com/img1.jpg","@type":"ImageObject"},
   {"url":"https://media.licdn.com/img2.jpg","@type":"ImageObject"}
 ]}
</script>
</head><body>
<meta property="og:description" content="Post body text here which is long enough to pass"/>
</body></html>
"""


def test_classify_links_returns_ld_json_images_when_no_dom_body():
    """When find_post_body_root returns None, images come from JSON-LD."""
    soup = BeautifulSoup(_POST_WITH_LD_JSON_IMAGES, "html.parser")
    urls, mentions, tags, imgs = classify_links_from_soup(
        soup, "https://www.linkedin.com/posts/x"
    )
    assert imgs == [
        "https://media.licdn.com/img1.jpg",
        "https://media.licdn.com/img2.jpg",
    ]
    assert urls == [] and mentions == [] and tags == []


def test_classify_links_supplements_ld_json_images_when_dom_has_none():
    """When DOM body exists but has no <img> tags, LD-JSON images fill in."""
    html = """
    <html><head>
    <script type="application/ld+json">
    {"@type":"SocialMediaPosting","image":[{"url":"https://cdn.example.com/photo.jpg","@type":"ImageObject"}]}
    </script>
    </head><body>
    <article data-id="x">
      <p class="feed-shared-text">Post body with enough content to exceed the minimum length check</p>
    </article>
    </body></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    _, _, _, imgs = classify_links_from_soup(soup, "https://www.linkedin.com/posts/x")
    assert imgs == ["https://cdn.example.com/photo.jpg"]


# --- comment stripping ---


def test_strip_trafilatura_comments_removes_comment_paragraphs():
    md = (
        "Post line one.\n\n"
        "Post line two.\n\n"
        "Very good [Author](https://linkedin.com/in/x?trk=public_post_comment-text)\n\n"
        "[Commenter](https://linkedin.com/in/c?trk=public_post_comment_actor-name)1mo\n\n"
        "Another comment body."
    )
    result = _strip_trafilatura_comments(md)
    assert result == "Post line one.\n\nPost line two."
    assert "public_post_comment" not in result


def test_strip_trafilatura_comments_leaves_clean_body_untouched():
    md = "Clean post.\n\nNo comments here.\n\n[Link](https://example.com?trk=public_post-text)"
    assert _strip_trafilatura_comments(md) == md


def test_strip_trafilatura_comments_handles_see_more_link():
    md = (
        "Post body.\n\n"
        "[See more comments](https://linkedin.com/signup?trk=public_post_see-more-comments)"
    )
    result = _strip_trafilatura_comments(md)
    assert result == "Post body."


def test_strip_trafilatura_comments_fallback_on_empty_result():
    """If stripping removes everything, the original is returned unchanged."""
    md = "Only [comment](https://linkedin.com/in/x?trk=public_post_comment-text) content."
    result = _strip_trafilatura_comments(md)
    assert result == md
