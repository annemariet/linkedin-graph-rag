"""
Code submission models for Code Review Assistant.
"""

import base64
import binascii
from datetime import datetime
from typing import Dict, List, Optional, Set

from pydantic import BaseModel, Field, validator

from src.core.config import get_settings
from src.models.base import BaseCodeReviewModel

settings = get_settings()

# Supported programming languages and file types
SUPPORTED_LANGUAGES = {
    "python": {"py"},
    "javascript": {"js", "jsx"},
    "typescript": {"ts", "tsx"},
    "java": {"java"},
    "csharp": {"cs"},
    "go": {"go"},
    "terraform": {"tf", "tfvars"},
    "sql": {"sql"},
    "yaml": {"yaml", "yml"},
    "markdown": {"md", "markdown"},
}

# Mapping of file extensions to languages
FILE_EXTENSION_TO_LANGUAGE = {
    ext: lang for lang, exts in SUPPORTED_LANGUAGES.items() for ext in exts
}

# Maximum file size in bytes (from settings in MB)
MAX_FILE_SIZE = settings.MAX_FILE_SIZE_MB * 1024 * 1024


class CodeFile(BaseCodeReviewModel):
    """Model representing a code file for review."""
    
    path: str = Field(..., description="Path to the file")
    content: str = Field(..., description="Content of the file")
    language: Optional[str] = Field(None, description="Programming language")
    file_type: Optional[str] = Field(None, description="File extension")
    encoding: str = Field("utf-8", description="File content encoding")
    is_base64: bool = Field(False, description="Whether content is base64 encoded")
    size: Optional[int] = Field(None, description="File size in bytes")
    
    @validator("path")
    def validate_path(cls, v: str) -> str:
        """Validate file path."""
        if not v or v.isspace():
            raise ValueError("File path cannot be empty")
        return v.strip()
    
    @validator("file_type", pre=True, always=True)
    def set_file_type(cls, v: Optional[str], values: Dict) -> str:
        """Set file type from path if not provided."""
        if v:
            return v.lower()
        
        path = values.get("path", "")
        if "." in path:
            return path.split(".")[-1].lower()
        return ""
    
    @validator("language", pre=True, always=True)
    def set_language(cls, v: Optional[str], values: Dict) -> Optional[str]:
        """Set language from file type if not provided."""
        if v:
            return v.lower()
        
        file_type = values.get("file_type", "")
        return FILE_EXTENSION_TO_LANGUAGE.get(file_type)
    
    @validator("content")
    def validate_content(cls, v: str, values: Dict) -> str:
        """Validate and decode content if base64 encoded."""
        is_base64 = values.get("is_base64", False)
        
        if is_base64:
            try:
                content = base64.b64decode(v).decode(values.get("encoding", "utf-8"))
                return content
            except (UnicodeDecodeError, binascii.Error) as e:
                raise ValueError(f"Invalid base64 content: {str(e)}")
        
        return v
    
    @validator("size", pre=True, always=True)
    def set_size(cls, v: Optional[int], values: Dict) -> int:
        """Set size from content if not provided."""
        if v is not None:
            return v
        
        content = values.get("content", "")
        return len(content.encode("utf-8"))
    
    @validator("size")
    def validate_size(cls, v: int) -> int:
        """Validate file size."""
        if v > MAX_FILE_SIZE:
            raise ValueError(
                f"File size ({v} bytes) exceeds maximum allowed size "
                f"({MAX_FILE_SIZE} bytes)"
            )
        return v


class ReviewConfiguration(BaseCodeReviewModel):
    """Model representing review configuration preferences."""
    
    style_analysis: bool = Field(True, description="Enable style analysis")
    security_analysis: bool = Field(True, description="Enable security analysis")
    performance_analysis: bool = Field(True, description="Enable performance analysis")
    test_analysis: bool = Field(True, description="Enable test analysis")
    
    style_rules: Dict[str, Dict] = Field(
        default_factory=dict, description="Custom style rules by language"
    )
    security_severity_threshold: str = Field(
        "low", description="Minimum security severity to report"
    )
    performance_threshold: str = Field(
        "medium", description="Performance issue threshold"
    )
    test_coverage_threshold: float = Field(
        80.0, description="Minimum test coverage percentage"
    )
    
    @validator("security_severity_threshold")
    def validate_security_threshold(cls, v: str) -> str:
        """Validate security severity threshold."""
        valid_values = {"critical", "high", "medium", "low"}
        if v.lower() not in valid_values:
            raise ValueError(
                f"Security severity threshold must be one of: {', '.join(valid_values)}"
            )
        return v.lower()
    
    @validator("performance_threshold")
    def validate_performance_threshold(cls, v: str) -> str:
        """Validate performance threshold."""
        valid_values = {"high", "medium", "low"}
        if v.lower() not in valid_values:
            raise ValueError(
                f"Performance threshold must be one of: {', '.join(valid_values)}"
            )
        return v.lower()
    
    @validator("test_coverage_threshold")
    def validate_test_coverage(cls, v: float) -> float:
        """Validate test coverage threshold."""
        if not 0 <= v <= 100:
            raise ValueError("Test coverage threshold must be between 0 and 100")
        return v


class CodeSubmission(BaseCodeReviewModel):
    """Model representing a code submission for review."""
    
    session_id: Optional[str] = Field(None, description="Unique session identifier")
    files: List[CodeFile] = Field(..., description="List of code files to review")
    configuration: ReviewConfiguration = Field(
        default_factory=ReviewConfiguration, description="Review configuration"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Submission timestamp"
    )
    
    @validator("files")
    def validate_files(cls, v: List[CodeFile]) -> List[CodeFile]:
        """Validate files list."""
        if not v:
            raise ValueError("At least one file must be provided")
        
        # Check for duplicate paths
        paths = [file.path for file in v]
        if len(paths) != len(set(paths)):
            raise ValueError("Duplicate file paths are not allowed")
        
        return v
    
    @validator("session_id", pre=True, always=True)
    def set_session_id(cls, v: Optional[str]) -> str:
        """Generate session ID if not provided."""
        if v:
            return v
        
        import uuid
        return str(uuid.uuid4())