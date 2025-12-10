"""Tests for activity_utils module."""

from linkedin_api.activity_utils import (
    extract_element_fields,
    determine_post_type,
    extract_reaction_type,
    extract_timestamp,
    is_reaction_element,
    is_post_element,
    is_comment_element,
    is_message_element,
    is_invitation_element,
)


class TestExtractElementFields:
    """Tests for extract_element_fields function."""

    def test_extracts_all_fields(self):
        element = {
            "resourceName": "ugcPosts",
            "methodName": "CREATE",
            "actor": "urn:li:person:123",
            "activity": {"id": "post-123", "created": {"time": 1609459200000}},
        }

        fields = extract_element_fields(element)

        assert fields["resource_name"] == "ugcPosts"
        assert fields["method_name"] == "CREATE"
        assert fields["actor"] == "urn:li:person:123"
        assert fields["activity"] == element["activity"]
        assert fields["timestamp"] == 1609459200000

    def test_handles_missing_fields(self):
        element = {"resourceName": "test"}

        fields = extract_element_fields(element)

        assert fields["resource_name"] == "test"
        assert fields["method_name"] == ""
        assert fields["actor"] == ""
        assert fields["activity"] == {}
        assert fields["timestamp"] is None

    def test_actor_from_activity(self):
        element = {"resourceName": "test", "activity": {"actor": "urn:li:person:456"}}

        fields = extract_element_fields(element)

        assert fields["actor"] == "urn:li:person:456"


class TestDeterminePostType:
    """Tests for determine_post_type function."""

    def test_original_post(self):
        activity = {"id": "urn:li:ugcPost:123", "ugcOrigin": "ORIGINAL"}

        post_type = determine_post_type(activity)

        assert post_type == "original"

    def test_repost_without_commentary(self):
        activity = {
            "id": "urn:li:ugcPost:123",
            "ugcOrigin": "RESHARE",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {"shareCommentary": {}}
            },
        }

        post_type = determine_post_type(activity)

        assert post_type == "repost"

    def test_repost_with_commentary(self):
        activity = {
            "id": "urn:li:ugcPost:123",
            "ugcOrigin": "RESHARE",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": "Great post!"}
                }
            },
        }

        post_type = determine_post_type(activity)

        assert post_type == "repost_with_comment"

    def test_repost_via_response_context(self):
        activity = {
            "id": "urn:li:ugcPost:123",
            "responseContext": {"parent": "urn:li:ugcPost:456"},
        }

        post_type = determine_post_type(activity)

        assert post_type == "repost"

    def test_repost_with_text_field(self):
        activity = {
            "id": "urn:li:ugcPost:123",
            "ugcOrigin": "RESHARE",
            "text": "My comment",
        }

        post_type = determine_post_type(activity)

        assert post_type == "repost_with_comment"


class TestExtractReactionType:
    """Tests for extract_reaction_type function."""

    def test_extracts_reaction_type(self):
        activity = {"reactionType": "LIKE"}

        reaction_type = extract_reaction_type(activity)

        assert reaction_type == "LIKE"

    def test_defaults_to_unknown(self):
        activity = {}

        reaction_type = extract_reaction_type(activity)

        assert reaction_type == "UNKNOWN"


class TestExtractTimestamp:
    """Tests for extract_timestamp function."""

    def test_extracts_timestamp(self):
        activity = {"created": {"time": 1609459200000}}

        timestamp = extract_timestamp(activity)

        assert timestamp == 1609459200000

    def test_handles_missing_timestamp(self):
        activity = {}

        timestamp = extract_timestamp(activity)

        assert timestamp is None

    def test_converts_to_iso(self):
        activity = {"created": {"time": 1609459200000}}

        iso = extract_timestamp(activity, as_iso=True)

        assert iso == "2021-01-01T00:00:00"


class TestElementTypeDetection:
    """Tests for element type detection functions."""

    def test_is_reaction_element(self):
        element = {"resourceName": "socialActions/likes"}
        assert is_reaction_element(element) is True

        element = {"resourceName": "reactions"}
        assert is_reaction_element(element) is True

        element = {"resourceName": "ugcPosts"}
        assert is_reaction_element(element) is False

    def test_is_post_element(self):
        element = {"resourceName": "ugcPosts"}
        assert is_post_element(element) is True

        element = {"resourceName": "ugcPost"}
        assert is_post_element(element) is True

        element = {"resourceName": "socialActions/likes"}
        assert is_post_element(element) is False

    def test_is_comment_element(self):
        element = {"resourceName": "socialActions/comments"}
        assert is_comment_element(element) is True

        element = {"resourceName": "comments"}
        assert is_comment_element(element) is True

        element = {"resourceName": "ugcPosts"}
        assert is_comment_element(element) is False

    def test_is_message_element(self):
        element = {"resourceName": "messages"}
        assert is_message_element(element) is True

        element = {"resourceName": "conversations"}
        assert is_message_element(element) is False

    def test_is_invitation_element(self):
        element = {"resourceName": "invitations"}
        assert is_invitation_element(element) is True

        element = {"resourceName": "invitation"}
        assert is_invitation_element(element) is True

        element = {"resourceName": "ugcPosts"}
        assert is_invitation_element(element) is False
