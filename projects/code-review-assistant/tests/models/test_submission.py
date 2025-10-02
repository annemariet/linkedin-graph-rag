"""
Tests for submission models.
"""

import base64
import pytest
from pydantic import ValidationError

from src.models.submission import (
    CodeFile,
    CodeSubmission,
    ReviewConfiguration,
    SUPPORTED_LANGUAGES,
    FILE_EXTENSION_TO_LANGUAGE,
)


class TestCodeFile:
    """Tests for CodeFile model."""
    
    def test_valid_code_file(self):
        """Test creating a valid CodeFile."""
        file = CodeFile(
            path="test.py",
            content="def hello(): return 'world'",
        )
        
        assert file.path == "test.py"
        assert file.content == "def hello(): return 'world'"
        assert file.language == "python"
        assert file.file_type == "py"
        assert file.encoding == "utf-8"
        assert file.is_base64 is False
        assert file.size == len("def hello(): return 'world'".encode("utf-8"))
    
    def test_base64_content(self):
        """Test CodeFile with base64 encoded content."""
        content = "def hello(): return 'world'"
        b64_content = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        
        file = CodeFile(
            path="test.py",
            content=b64_content,
            is_base64=True,
        )
        
        assert file.content == content
    
    def test_invalid_base64_content(self):
        """Test CodeFile with invalid base64 content."""
        with pytest.raises(ValidationError):
            CodeFile(
                path="test.py",
                content="not-valid-base64!",
                is_base64=True,
            )
    
    def test_empty_path(self):
        """Test CodeFile with empty path."""
        with pytest.raises(ValidationError):
            CodeFile(
                path="",
                content="def hello(): return 'world'",
            )
    
    def test_file_too_large(self):
        """Test CodeFile with content that's too large."""
        from src.models.submission import MAX_FILE_SIZE
        
        # Create a string that's larger than the max file size
        large_content = "x" * (MAX_FILE_SIZE + 1)
        
        with pytest.raises(ValidationError):
            CodeFile(
                path="large_file.py",
                content=large_content,
            )
    
    def test_language_detection(self):
        """Test language detection from file extension."""
        for lang, extensions in SUPPORTED_LANGUAGES.items():
            for ext in extensions:
                file = CodeFile(
                    path=f"test.{ext}",
                    content="content",
                )
                assert file.language == lang
                assert file.file_type == ext


class TestReviewConfiguration:
    """Tests for ReviewConfiguration model."""
    
    def test_default_configuration(self):
        """Test default ReviewConfiguration."""
        config = ReviewConfiguration()
        
        assert config.style_analysis is True
        assert config.security_analysis is True
        assert config.performance_analysis is True
        assert config.test_analysis is True
        assert config.security_severity_threshold == "low"
        assert config.performance_threshold == "medium"
        assert config.test_coverage_threshold == 80.0
    
    def test_custom_configuration(self):
        """Test custom ReviewConfiguration."""
        config = ReviewConfiguration(
            style_analysis=False,
            security_severity_threshold="high",
            test_coverage_threshold=90.0,
        )
        
        assert config.style_analysis is False
        assert config.security_analysis is True
        assert config.security_severity_threshold == "high"
        assert config.test_coverage_threshold == 90.0
    
    def test_invalid_security_threshold(self):
        """Test invalid security severity threshold."""
        with pytest.raises(ValidationError):
            ReviewConfiguration(security_severity_threshold="invalid")
    
    def test_invalid_performance_threshold(self):
        """Test invalid performance threshold."""
        with pytest.raises(ValidationError):
            ReviewConfiguration(performance_threshold="invalid")
    
    def test_invalid_test_coverage(self):
        """Test invalid test coverage threshold."""
        with pytest.raises(ValidationError):
            ReviewConfiguration(test_coverage_threshold=101)
        
        with pytest.raises(ValidationError):
            ReviewConfiguration(test_coverage_threshold=-1)


class TestCodeSubmission:
    """Tests for CodeSubmission model."""
    
    def test_valid_submission(self):
        """Test creating a valid CodeSubmission."""
        submission = CodeSubmission(
            files=[
                CodeFile(path="test.py", content="def hello(): return 'world'"),
                CodeFile(path="test.js", content="function hello() { return 'world'; }"),
            ],
        )
        
        assert submission.session_id is not None
        assert len(submission.files) == 2
        assert isinstance(submission.configuration, ReviewConfiguration)
        assert submission.timestamp is not None
    
    def test_custom_session_id(self):
        """Test CodeSubmission with custom session ID."""
        submission = CodeSubmission(
            session_id="test-session",
            files=[CodeFile(path="test.py", content="content")],
        )
        
        assert submission.session_id == "test-session"
    
    def test_empty_files(self):
        """Test CodeSubmission with empty files list."""
        with pytest.raises(ValidationError):
            CodeSubmission(files=[])
    
    def test_duplicate_file_paths(self):
        """Test CodeSubmission with duplicate file paths."""
        with pytest.raises(ValidationError):
            CodeSubmission(
                files=[
                    CodeFile(path="test.py", content="content1"),
                    CodeFile(path="test.py", content="content2"),
                ],
            )
    
    def test_custom_configuration(self):
        """Test CodeSubmission with custom configuration."""
        config = ReviewConfiguration(
            style_analysis=False,
            security_severity_threshold="high",
        )
        
        submission = CodeSubmission(
            files=[CodeFile(path="test.py", content="content")],
            configuration=config,
        )
        
        assert submission.configuration.style_analysis is False
        assert submission.configuration.security_severity_threshold == "high"