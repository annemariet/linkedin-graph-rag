from collections import defaultdict

from linkedin_api.extract_graph_data import process_comment
from linkedin_api.utils.urns import build_comment_urn, comment_urn_to_post_url


def _run_process_comment(activity, element):
    people = {}
    posts = {}
    comments = {}
    relationships = []
    skipped = defaultdict(int)

    process_comment(
        element, activity, people, posts, comments, relationships, skipped
    )
    return people, posts, comments, relationships, skipped


def test_top_level_comment_links_to_post_and_creates_comment():
    post_urn = "urn:li:ugcPost:7409540812340097024"
    comment_id = "7410301301244284929"
    actor = "urn:li:person:k_ho7OlN0r"
    activity = {
        "id": comment_id,
        "object": post_urn,
        "message": {"text": "Merci pour ce partage !"},
        "created": {"time": 1766750428159},
    }
    element = {"resourceName": "socialActions/comments", "actor": actor}

    _, _, comments, relationships, skipped = _run_process_comment(activity, element)

    comment_urn = build_comment_urn(post_urn, comment_id)
    assert comment_urn in comments
    assert skipped == {}

    assert {
        "type": "CREATES",
        "from": actor,
        "to": comment_urn,
    } in [
        {"type": r["type"], "from": r["from"], "to": r["to"]}
        for r in relationships
    ]
    assert {
        "type": "COMMENTS_ON",
        "from": comment_urn,
        "to": post_urn,
    } in [
        {"type": r["type"], "from": r["from"], "to": r["to"]}
        for r in relationships
    ]


def test_reply_comment_links_to_parent_comment_urn():
    post_urn = "urn:li:ugcPost:7409540812340097024"
    parent_comment_id = "7410288387825459200"
    parent_comment_urn = build_comment_urn(post_urn, parent_comment_id)
    comment_id = "7410301301244284929"
    actor = "urn:li:person:k_ho7OlN0r"
    activity = {
        "id": comment_id,
        "object": post_urn,
        "message": {"text": "Thanks!"},
        "created": {"time": 1766750428159},
        "responseContext": {"parent": parent_comment_urn},
    }
    element = {"resourceName": "socialActions/comments", "actor": actor}

    _, _, comments, relationships, skipped = _run_process_comment(activity, element)

    comment_urn = build_comment_urn(post_urn, comment_id)
    assert comment_urn in comments
    assert parent_comment_urn in comments
    assert skipped == {}

    assert {
        "type": "COMMENTS_ON",
        "from": comment_urn,
        "to": parent_comment_urn,
    } in [
        {"type": r["type"], "from": r["from"], "to": r["to"]}
        for r in relationships
    ]
    assert {
        "type": "COMMENTS_ON",
        "from": comment_urn,
        "to": post_urn,
    } not in [
        {"type": r["type"], "from": r["from"], "to": r["to"]}
        for r in relationships
    ]

    expected_url = comment_urn_to_post_url(parent_comment_urn) or ""
    assert comments[parent_comment_urn]["properties"]["url"] == expected_url


def test_reply_comment_links_when_parent_id_only():
    post_urn = "urn:li:ugcPost:7409540812340097024"
    parent_comment_id = "7410288387825459200"
    parent_comment_urn = build_comment_urn(post_urn, parent_comment_id)
    comment_id = "7410301301244284929"
    actor = "urn:li:person:k_ho7OlN0r"
    activity = {
        "id": comment_id,
        "object": post_urn,
        "message": {"text": "Reply"},
        "created": {"time": 1766750428159},
        "responseContext": {"parentCommentId": parent_comment_id},
    }
    element = {"resourceName": "socialActions/comments", "actor": actor}

    _, _, comments, relationships, skipped = _run_process_comment(activity, element)

    comment_urn = build_comment_urn(post_urn, comment_id)
    assert comment_urn in comments
    assert parent_comment_urn in comments
    assert skipped == {}

    assert {
        "type": "COMMENTS_ON",
        "from": comment_urn,
        "to": parent_comment_urn,
    } in [
        {"type": r["type"], "from": r["from"], "to": r["to"]}
        for r in relationships
    ]
