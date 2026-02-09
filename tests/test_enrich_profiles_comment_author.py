"""Tests for comment author extraction from post HTML."""

from linkedin_api.enrich_profiles import parse_comment_author_from_html


def test_parse_comment_author_from_html_finds_author_in_comment_block():
    html = """
    <div class="comments">
        <div class="comment">
            <a href="https://www.linkedin.com/in/commenter-name?actor-name">Commenter Name</a>
            <p>This is the comment text we are looking for.</p>
        </div>
    </div>
    """
    author = parse_comment_author_from_html(
        html, "This is the comment text we are looking for."
    )
    assert author is not None
    assert author["name"] == "Commenter Name"
    assert "linkedin.com/in/" in author["profile_url"]
    assert (
        "actor-name" not in author["profile_url"]
        or "?" not in author["profile_url"].split("/in/")[-1]
    )


def test_parse_comment_author_from_html_returns_none_for_empty_text():
    assert parse_comment_author_from_html("<p>x</p>", "") is None
    assert parse_comment_author_from_html("", "some text") is None


def test_parse_comment_author_from_html_returns_none_when_text_not_found():
    html = "<div><a href='/in/other'>Other</a><p>Different content</p></div>"
    assert parse_comment_author_from_html(html, "comment text not in page") is None
