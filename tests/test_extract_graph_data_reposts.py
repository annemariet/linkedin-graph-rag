"""Tests for repost extraction: author is the reposter (actor), not original post author."""

from collections import defaultdict

from linkedin_api.extract_graph_data import process_post


def _run_process_post(activity, element):
    people = {}
    posts = {}
    relationships = []
    skipped = defaultdict(int)
    process_post(element, activity, people, posts, relationships, skipped)
    return people, posts, relationships, skipped


def test_repost_author_is_actor_not_original_author():
    """Repost CREATES relationship must be from the reposter (actor), not firstPublishedActor."""
    repost_urn = "urn:li:share:123"
    original_urn = "urn:li:ugcPost:7409540812340097024"
    reposter_actor = "urn:li:person:reposter"
    original_author = "urn:li:person:original_author"
    activity = {
        "id": repost_urn,
        "author": original_author,
        "firstPublishedActor": {"member": original_author},
        "ugcOrigin": "RESHARE",
        "responseContext": {"parent": original_urn},
        "created": {"time": 1766750428159},
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {"shareCommentary": {"text": ""}},
        },
    }
    element = {"resourceName": "ugcPosts", "actor": reposter_actor}

    people, posts, relationships, skipped = _run_process_post(activity, element)

    assert skipped == {}
    assert repost_urn in posts
    reposter_to_share = [
        r
        for r in relationships
        if r["type"] == "REPOSTS"
        and r["from"] == reposter_actor
        and r["to"] == repost_urn
    ]
    assert (
        len(reposter_to_share) == 1
    ), "Reposter (actor) must have REPOSTS to the repost share node"
    share_to_original = [
        r
        for r in relationships
        if r["type"] == "REPOSTS"
        and r["from"] == repost_urn
        and r["to"] == original_urn
    ]
    assert len(share_to_original) == 1
    assert reposter_actor in people
