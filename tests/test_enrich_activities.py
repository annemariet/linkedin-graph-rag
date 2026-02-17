"""Tests for enrich_activities module."""

import responses

from linkedin_api.enrich_activities import _fetch_with_requests, _is_comment_feed_url


class TestFetchWithRequests:
    @responses.activate
    def test_returns_content_on_200_with_post_body(self):
        html = """<!DOCTYPE html><html><head><title>Post</title></head><body>
        <article data-id="123"><div class="feed-shared-text">
        Check out this article about AI and machine learning: https://example.com/blog/post
        </div></article>
        </body></html>"""
        responses.add(responses.GET, "https://example.com/post", body=html, status=200)
        result = _fetch_with_requests("https://example.com/post")
        assert result is not None
        content, urls = result
        assert len(content) >= 50
        assert any("example.com" in u for u in urls)

    @responses.activate
    def test_returns_none_on_403(self):
        responses.add(
            responses.GET,
            "https://linkedin.com/feed/update/urn:li:activity:123",
            status=403,
        )
        assert (
            _fetch_with_requests("https://linkedin.com/feed/update/urn:li:activity:123")
            is None
        )

    @responses.activate
    def test_returns_none_on_sign_in_title(self):
        html = """<!DOCTYPE html><html><head><title>Sign In | LinkedIn</title></head><body></body></html>"""
        responses.add(
            responses.GET,
            "https://linkedin.com/feed/update/urn:li:activity:123",
            body=html,
            status=200,
        )
        assert (
            _fetch_with_requests("https://linkedin.com/feed/update/urn:li:activity:123")
            is None
        )

    @responses.activate
    def test_returns_none_on_login_title(self):
        html = """<!DOCTYPE html><html><head><title>Login to LinkedIn</title></head><body></body></html>"""
        responses.add(
            responses.GET,
            "https://linkedin.com/feed/update/urn:li:activity:456",
            body=html,
            status=200,
        )
        assert (
            _fetch_with_requests("https://linkedin.com/feed/update/urn:li:activity:456")
            is None
        )

    @responses.activate
    def test_returns_none_on_empty_content(self):
        html = """<!DOCTYPE html><html><head><title>LinkedIn</title></head><body><p>Hi</p></body></html>"""
        responses.add(responses.GET, "https://linkedin.com/post", body=html, status=200)
        assert _fetch_with_requests("https://linkedin.com/post") is None


class TestIsCommentFeedUrl:
    def test_comment_urn_in_url(self):
        assert (
            _is_comment_feed_url(
                "https://linkedin.com/feed/update/urn:li:comment:(activity:123,456)"
            )
            is True
        )

    def test_post_urn_in_url(self):
        assert (
            _is_comment_feed_url("https://linkedin.com/feed/update/urn:li:activity:123")
            is False
        )
