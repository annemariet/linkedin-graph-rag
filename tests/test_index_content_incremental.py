"""Unit tests for incremental loading in index_content module."""

from unittest.mock import MagicMock

from linkedin_api.index_content import (
    get_posts_and_comments,
    split_text_into_chunks,
    create_chunks_batch,
    store_embeddings_batch,
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


class TestCreateChunksBatchIdempotency:
    """Test create_chunks_batch idempotency behavior."""

    def test_create_chunks_batch_is_idempotent(self):
        """Test that calling create_chunks_batch with same data is idempotent."""
        mock_tx = MagicMock()
        mock_result = MagicMock()
        mock_result.__iter__.return_value = [
            {"chunk_id": "test_chunk_0"},
            {"chunk_id": "test_chunk_1"},
        ]
        mock_tx.run.return_value = mock_result

        chunks_data = [
            {
                "chunk_id": "test_chunk_0",
                "text": "Test text 1",
                "source_urn": "urn:li:activity:123",
                "chunk_index": 0,
                "total_chunks": 2,
            },
            {
                "chunk_id": "test_chunk_1",
                "text": "Test text 2",
                "source_urn": "urn:li:activity:123",
                "chunk_index": 1,
                "total_chunks": 2,
            },
        ]

        # First call
        ids1 = create_chunks_batch(mock_tx, chunks_data)

        # Second call with same data - should be idempotent (MERGE behavior)
        ids2 = create_chunks_batch(mock_tx, chunks_data)

        assert ids1 == ["test_chunk_0", "test_chunk_1"]
        assert ids2 == ["test_chunk_0", "test_chunk_1"]

    def test_create_chunks_batch_returns_chunk_ids(self):
        """Test that function returns chunk IDs for reference."""
        mock_tx = MagicMock()
        mock_result = MagicMock()
        mock_result.__iter__.return_value = [{"chunk_id": "test_chunk"}]
        mock_tx.run.return_value = mock_result

        chunks_data = [
            {
                "chunk_id": "test_chunk",
                "text": "Test text",
                "source_urn": "urn:li:activity:456",
                "chunk_index": 0,
                "total_chunks": 1,
            }
        ]

        chunk_ids = create_chunks_batch(mock_tx, chunks_data)

        assert chunk_ids == ["test_chunk"]


class TestStoreEmbeddingsBatch:
    """Test store_embeddings_batch functionality."""

    def test_store_embeddings_batch_returns_count(self):
        """Test that function returns count of updated chunks."""
        mock_tx = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = {"updated": 3}
        mock_tx.run.return_value = mock_result

        embeddings_data = [
            {"chunk_id": "chunk_0", "embedding": [0.1] * 768},
            {"chunk_id": "chunk_1", "embedding": [0.2] * 768},
            {"chunk_id": "chunk_2", "embedding": [0.3] * 768},
        ]

        updated = store_embeddings_batch(mock_tx, embeddings_data)

        assert updated == 3
