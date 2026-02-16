"""Tests for utils.urls module."""

from linkedin_api.utils.urls import get_urls_from_post_and_first_comment


def test_get_urls_from_post_and_first_comment_post_only():
    """URLs from post content when no matching first comment."""
    nodes = {
        "urn:li:person:author": {"labels": ["Person"], "properties": {}},
        "urn:li:activity:123": {
            "labels": ["Post"],
            "properties": {
                "content": "Check this https://example.com/page",
                "extracted_urls": ["https://example.com/page"],
            },
        },
    }
    rels = [
        {
            "type": "CREATES",
            "from": "urn:li:person:author",
            "to": "urn:li:activity:123",
        },
    ]
    urls = get_urls_from_post_and_first_comment(nodes, rels, "urn:li:activity:123")
    assert urls == ["https://example.com/page"]


def test_get_urls_from_first_author_comment():
    """URLs from first comment when author matches post author."""
    nodes = {
        "urn:li:person:author": {"labels": ["Person"], "properties": {}},
        "urn:li:activity:123": {
            "labels": ["Post"],
            "properties": {"content": "Teaser text", "extracted_urls": []},
        },
        "urn:li:comment:(activity:123,456)": {
            "labels": ["Comment"],
            "properties": {
                "text": "Full article: https://blog.example.com/post",
                "timestamp": 1000,
            },
        },
    }
    rels = [
        {
            "type": "CREATES",
            "from": "urn:li:person:author",
            "to": "urn:li:activity:123",
        },
        {
            "type": "CREATES",
            "from": "urn:li:person:author",
            "to": "urn:li:comment:(activity:123,456)",
        },
        {
            "type": "COMMENTS_ON",
            "from": "urn:li:comment:(activity:123,456)",
            "to": "urn:li:activity:123",
        },
    ]
    urls = get_urls_from_post_and_first_comment(nodes, rels, "urn:li:activity:123")
    assert "https://blog.example.com/post" in urls


def test_no_urls_when_first_comment_by_different_author():
    """First comment by someone else: do not add its URLs."""
    nodes = {
        "urn:li:person:author": {"labels": ["Person"], "properties": {}},
        "urn:li:person:other": {"labels": ["Person"], "properties": {}},
        "urn:li:activity:123": {
            "labels": ["Post"],
            "properties": {"content": "", "extracted_urls": []},
        },
        "urn:li:comment:(activity:123,456)": {
            "labels": ["Comment"],
            "properties": {
                "text": "Link from other: https://other.com",
                "timestamp": 1000,
            },
        },
    }
    rels = [
        {
            "type": "CREATES",
            "from": "urn:li:person:author",
            "to": "urn:li:activity:123",
        },
        {
            "type": "CREATES",
            "from": "urn:li:person:other",
            "to": "urn:li:comment:(activity:123,456)",
        },
        {
            "type": "COMMENTS_ON",
            "from": "urn:li:comment:(activity:123,456)",
            "to": "urn:li:activity:123",
        },
    ]
    urls = get_urls_from_post_and_first_comment(nodes, rels, "urn:li:activity:123")
    assert "https://other.com" not in urls
