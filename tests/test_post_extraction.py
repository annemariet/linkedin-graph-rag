"""Tests for linkedin_api.post_extraction."""

from bs4 import BeautifulSoup

from linkedin_api.post_extraction import (
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
