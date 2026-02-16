"""Tests for comment vs post routing (_is_comment_like_activity and extraction_preview)."""

from linkedin_api.extract_graph_data import _is_comment_like_activity
from linkedin_api.extraction_preview import extract_element_preview


def test_is_comment_like_activity_comment_shape_returns_true():
    activity = {
        "id": "7410301301244284929",
        "object": "urn:li:ugcPost:7409540812340097024",
        "message": {"text": "A comment"},
    }
    assert _is_comment_like_activity(activity) is True


def test_is_comment_like_activity_post_share_returns_false():
    activity = {
        "id": "urn:li:share:123",
        "specificContent": {"com.linkedin.ugc.ShareContent": {"shareCommentary": {}}},
    }
    assert _is_comment_like_activity(activity) is False


def test_is_comment_like_activity_no_message_returns_false():
    activity = {"object": "urn:li:ugcPost:123"}
    assert _is_comment_like_activity(activity) is False


def test_comment_like_under_post_resource_routes_to_comment():
    """When resourceName is ugcPosts but activity is comment-like, primary is 'comment'."""
    element = {
        "resourceName": "ugcPosts",
        "actor": "urn:li:person:abc",
        "activity": {
            "id": "7410301301244284929",
            "object": "urn:li:ugcPost:7409540812340097024",
            "message": {"text": "A comment"},
            "created": {"time": 1766750428159},
        },
    }
    result = extract_element_preview(element)
    assert result["extracted"]["primary"] == "comment"
    nodes = result["extracted"]["nodes"]
    comment_nodes = [n for n in nodes if n.get("label") == "Comment"]
    assert len(comment_nodes) >= 1
