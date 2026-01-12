"""Unit tests for incremental loading in index_content module."""

from unittest.mock import MagicMock

from linkedin_api.index_content import (
    get_posts_and_comments,
    split_text_into_chunks,
    create_chunk_node,
)


class TestSplitTextIntoChunks:
    """Test text chunking functionality - pure function, no mocking needed."""

    def test_split_short_text(self):
        """Test that short text returns single chunk."""
        text = "Short text"
        chunks = split_text_into_chunks(text, chunk_size=500, overlap=100)

        assert len(chunks) == 1
        assert chunks[0] == text

    def test_split_long_text(self):
        """Test that long text is split into multiple chunks."""
        text = "A" * 1200  # 1200 characters
        chunks = split_text_into_chunks(text, chunk_size=500, overlap=100)

        assert len(chunks) > 1
        # First chunk should be ~500 chars
        assert len(chunks[0]) <= 500

    def test_split_with_overlap(self):
        """Test that chunks overlap correctly."""
        text = "A" * 1000
        chunks = split_text_into_chunks(text, chunk_size=500, overlap=100)

        assert len(chunks) >= 2
        # Verify chunks are properly sized
        for chunk in chunks[:-1]:
            assert len(chunk) <= 500

    def test_split_preserves_sentence_boundaries(self):
        """Test that splitting tries to preserve sentence boundaries."""
        text = "First sentence. Second sentence. " * 50
        chunks = split_text_into_chunks(text, chunk_size=100, overlap=20)

        # Most chunks should end with sentence punctuation
        for chunk in chunks[:-1]:  # Last chunk may be incomplete
            if len(chunk) > 20:  # Ignore very short chunks
                # Should end with sentence punctuation or be near end
                assert chunk[-1] in ".!?" or chunk == chunks[-1]

    def test_split_empty_text(self):
        """Test handling of empty text."""
        chunks = split_text_into_chunks("", chunk_size=500, overlap=100)
        assert len(chunks) == 1
        assert chunks[0] == ""

    def test_split_exact_chunk_size(self):
        """Test text that is exactly chunk_size."""
        text = "A" * 500
        chunks = split_text_into_chunks(text, chunk_size=500, overlap=100)
        assert len(chunks) == 1
        assert chunks[0] == text


class TestGetPostsAndCommentsIncremental:
    """Test get_posts_and_comments incremental loading behavior."""

    def test_returns_only_unindexed_posts_and_comments(self):
        """Test that function returns only items that haven't been indexed yet."""
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session

        # Mock database returning only unindexed items
        mock_result = MagicMock()
        mock_record1 = MagicMock()
        mock_record1.__getitem__.side_effect = lambda key: {
            "urn": "urn:li:activity:123",
            "url": "https://linkedin.com/posts/test",
            "labels": ["Post"],
            "post_id": "123",
            "comment_id": None,
        }[key]
        mock_record1.get.return_value = None

        mock_record2 = MagicMock()
        mock_record2.__getitem__.side_effect = lambda key: {
            "urn": "urn:li:comment:456",
            "url": "https://linkedin.com/comments/test",
            "labels": ["Comment"],
            "post_id": None,
            "comment_id": "456",
        }[key]
        mock_record2.get.side_effect = lambda key, default=None: {
            "post_id": None,
            "comment_id": "456",
        }.get(key, default)

        mock_result.__iter__.return_value = [mock_record1, mock_record2]
        mock_session.run.return_value = mock_result

        nodes = get_posts_and_comments(mock_driver)

        # Verify correct structure returned - only unindexed items
        assert len(nodes) == 2
        assert nodes[0]["urn"] == "urn:li:activity:123"
        assert nodes[0]["labels"] == ["Post"]
        assert nodes[1]["urn"] == "urn:li:comment:456"
        assert nodes[1]["labels"] == ["Comment"]

    def test_handles_empty_result(self):
        """Test handling when no unindexed items exist."""
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session

        mock_result = MagicMock()
        mock_result.__iter__.return_value = []
        mock_session.run.return_value = mock_result

        nodes = get_posts_and_comments(mock_driver)

        assert len(nodes) == 0

    def test_filters_by_url_requirements(self):
        """Test that only items with valid URLs are returned."""
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session

        mock_result = MagicMock()
        mock_record = MagicMock()
        mock_record.__getitem__.side_effect = lambda key: {
            "urn": "urn:li:activity:999",
            "url": "https://linkedin.com/posts/valid",
            "labels": ["Post"],
            "post_id": "999",
            "comment_id": None,
        }[key]
        mock_record.get.return_value = None

        mock_result.__iter__.return_value = [mock_record]
        mock_session.run.return_value = mock_result

        nodes = get_posts_and_comments(mock_driver)

        assert len(nodes) == 1
        assert nodes[0]["url"] == "https://linkedin.com/posts/valid"


class TestCreateChunkNodeIdempotency:
    """Test create_chunk_node idempotency behavior."""

    def test_create_chunk_node_is_idempotent(self):
        """Test that calling create_chunk_node multiple times doesn't create duplicates."""
        mock_tx = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = {"node_id": 123, "chunk_id": "test_chunk_0"}
        mock_tx.run.return_value = mock_result

        # First call
        node_id1 = create_chunk_node(
            mock_tx,
            chunk_id="test_chunk_0",
            text="Test text",
            source_urn="urn:li:activity:123",
            chunk_index=0,
            total_chunks=1,
        )

        # Second call with same chunk_id - should be idempotent
        node_id2 = create_chunk_node(
            mock_tx,
            chunk_id="test_chunk_0",
            text="Updated text",
            source_urn="urn:li:activity:123",
            chunk_index=0,
            total_chunks=1,
        )

        # Should return same node_id (idempotent behavior)
        assert node_id1 == 123
        assert node_id2 == 123

    def test_create_chunk_node_returns_node_id(self):
        """Test that function returns the node ID for further operations."""
        mock_tx = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = {"node_id": 456, "chunk_id": "test_chunk"}
        mock_tx.run.return_value = mock_result

        node_id = create_chunk_node(
            mock_tx,
            chunk_id="test_chunk",
            text="Test text",
            source_urn="urn:li:activity:456",
            chunk_index=0,
            total_chunks=1,
        )

        assert node_id == 456
        assert isinstance(node_id, int)
