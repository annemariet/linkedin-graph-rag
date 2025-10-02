"""
Custom exceptions for Code Review Assistant.
"""


class CodeReviewError(Exception):
    """Base exception for Code Review Assistant."""
    pass


class ValidationError(CodeReviewError):
    """Exception raised for validation errors."""
    pass


class AnalysisError(CodeReviewError):
    """Exception raised during code analysis."""
    pass


class AgentError(CodeReviewError):
    """Exception raised by agents."""
    pass


class ConfigurationError(CodeReviewError):
    """Exception raised for configuration errors."""
    pass


class ToolIntegrationError(CodeReviewError):
    """Exception raised for tool integration errors."""
    pass


class TimeoutError(CodeReviewError):
    """Exception raised when operations timeout."""
    pass