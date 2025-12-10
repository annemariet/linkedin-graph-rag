"""Tests for changelog_utils module."""

from unittest.mock import MagicMock, patch

from linkedin_api.changelog_utils import (
    BASE_URL,
    fetch_changelog_data,
    get_changelog_session,
)


class TestFetchChangelogData:
    """Test fetch_changelog_data function."""

    @patch("linkedin_api.changelog_utils.get_access_token")
    @patch("linkedin_api.changelog_utils.build_linkedin_session")
    def test_fetch_all_data_with_pagination(self, mock_build_session, mock_get_token):
        """Test fetching all changelog data with pagination."""
        mock_get_token.return_value = "test_token"
        mock_session = MagicMock()
        mock_build_session.return_value = mock_session

        # Mock first page
        mock_response_1 = MagicMock()
        mock_response_1.status_code = 200
        mock_response_1.json.return_value = {
            "elements": [{"id": 1}, {"id": 2}],
            "paging": {"links": [{"rel": "next", "href": "next_page"}]},
        }

        # Mock second page
        mock_response_2 = MagicMock()
        mock_response_2.status_code = 200
        mock_response_2.json.return_value = {
            "elements": [{"id": 3}],
            "paging": {"links": []},
        }

        mock_session.get.side_effect = [mock_response_1, mock_response_2]

        result = fetch_changelog_data()

        assert len(result) == 3
        assert result[0]["id"] == 1
        assert result[1]["id"] == 2
        assert result[2]["id"] == 3
        assert mock_session.get.call_count == 2

    @patch("linkedin_api.changelog_utils.get_access_token")
    @patch("linkedin_api.changelog_utils.build_linkedin_session")
    def test_fetch_with_resource_filter(self, mock_build_session, mock_get_token):
        """Test fetching with resource name filtering."""
        mock_get_token.return_value = "test_token"
        mock_session = MagicMock()
        mock_build_session.return_value = mock_session

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "elements": [
                {"resourceName": "ugcPosts", "id": 1},
                {"resourceName": "messages", "id": 2},
                {"resourceName": "ugcPosts", "id": 3},
            ],
            "paging": {"links": []},
        }

        mock_session.get.return_value = mock_response

        result = fetch_changelog_data(resource_filter=["ugcPosts"])

        assert len(result) == 2
        assert all(e["resourceName"] == "ugcPosts" for e in result)

    @patch("linkedin_api.changelog_utils.get_access_token")
    def test_fetch_no_token(self, mock_get_token):
        """Test that missing token returns empty list."""
        mock_get_token.return_value = None

        result = fetch_changelog_data()

        assert result == []

    @patch("linkedin_api.changelog_utils.get_access_token")
    @patch("linkedin_api.changelog_utils.build_linkedin_session")
    def test_fetch_handles_api_error(self, mock_build_session, mock_get_token):
        """Test handling of API errors."""
        mock_get_token.return_value = "test_token"
        mock_session = MagicMock()
        mock_build_session.return_value = mock_session

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_session.get.return_value = mock_response

        result = fetch_changelog_data()

        assert result == []

    @patch("linkedin_api.changelog_utils.get_access_token")
    @patch("linkedin_api.changelog_utils.build_linkedin_session")
    def test_fetch_handles_exception(self, mock_build_session, mock_get_token):
        """Test handling of exceptions during fetch."""
        mock_get_token.return_value = "test_token"
        mock_session = MagicMock()
        mock_build_session.return_value = mock_session
        mock_session.get.side_effect = Exception("Network error")

        result = fetch_changelog_data()

        assert result == []


class TestGetChangelogSession:
    """Test get_changelog_session function."""

    @patch("linkedin_api.changelog_utils.get_access_token")
    @patch("linkedin_api.changelog_utils.build_linkedin_session")
    def test_get_session_success(self, mock_build_session, mock_get_token):
        """Test successful session creation."""
        mock_get_token.return_value = "test_token"
        mock_session = MagicMock()
        mock_build_session.return_value = mock_session

        result = get_changelog_session()

        assert result == mock_session
        mock_build_session.assert_called_once_with("test_token")

    @patch("linkedin_api.changelog_utils.get_access_token")
    def test_get_session_no_token(self, mock_get_token):
        """Test that missing token returns None."""
        mock_get_token.return_value = None

        result = get_changelog_session()

        assert result is None


class TestBaseUrl:
    """Test BASE_URL constant."""

    def test_base_url_constant(self):
        """Test that BASE_URL is correctly defined."""
        assert BASE_URL == "https://api.linkedin.com/rest"
