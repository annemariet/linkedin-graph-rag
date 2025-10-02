"""
Utility functions for Code Review Assistant.
"""

import hashlib
import uuid
from typing import Any, Dict, List, Optional


def generate_session_id() -> str:
    """Generate a unique session ID."""
    return str(uuid.uuid4())


def calculate_file_hash(content: str) -> str:
    """Calculate SHA-256 hash of file content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def sanitize_filename(filename: str) -> str:
    """Sanitize filename for safe storage."""
    # Remove or replace unsafe characters
    unsafe_chars = ['<', '>', ':', '"', '|', '?', '*', '\\', '/']
    sanitized = filename
    for char in unsafe_chars:
        sanitized = sanitized.replace(char, '_')
    return sanitized


def get_file_language(file_path: str) -> Optional[str]:
    """Determine programming language from file path."""
    from src.models.submission import FILE_EXTENSION_TO_LANGUAGE
    
    if '.' not in file_path:
        return None
    
    extension = file_path.split('.')[-1].lower()
    return FILE_EXTENSION_TO_LANGUAGE.get(extension)


def format_bytes(bytes_count: int) -> str:
    """Format bytes into human readable format."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_count < 1024.0:
            return f"{bytes_count:.1f} {unit}"
        bytes_count /= 1024.0
    return f"{bytes_count:.1f} TB"


def merge_dicts(dict1: Dict[str, Any], dict2: Dict[str, Any]) -> Dict[str, Any]:
    """Merge two dictionaries recursively."""
    result = dict1.copy()
    
    for key, value in dict2.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_dicts(result[key], value)
        else:
            result[key] = value
    
    return result