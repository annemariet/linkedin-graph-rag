"""
Analysis result models for Code Review Assistant.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from pydantic import Field, validator

from src.models.base import BaseCodeReviewModel


class Finding(BaseCodeReviewModel):
    """Model representing a single finding from code analysis."""
    
    category: str = Field(..., description="Finding category")
    severity: str = Field(..., description="Finding severity")
    file_path: str = Field(..., description="Path to the file with the finding")
    line_number: Optional[int] = Field(None, description="Line number of the finding")
    column: Optional[int] = Field(None, description="Column number of the finding")
    description: str = Field(..., description="Description of the finding")
    suggestion: str = Field(..., description="Suggestion to fix the finding")
    tool_source: str = Field(..., description="Tool that generated the finding")
    code_snippet: Optional[str] = Field(None, description="Code snippet with the issue")
    
    @validator("category")
    def validate_category(cls, v: str) -> str:
        """Validate finding category."""
        valid_categories = {"style", "security", "performance", "testing"}
        if v.lower() not in valid_categories:
            raise ValueError(
                f"Category must be one of: {', '.join(valid_categories)}"
            )
        return v.lower()
    
    @validator("severity")
    def validate_severity(cls, v: str) -> str:
        """Validate finding severity."""
        valid_severities = {"critical", "high", "medium", "low"}
        if v.lower() not in valid_severities:
            raise ValueError(
                f"Severity must be one of: {', '.join(valid_severities)}"
            )
        return v.lower()


class AnalysisResult(BaseCodeReviewModel):
    """Model representing the result of a code analysis by an agent."""
    
    agent_id: str = Field(..., description="ID of the agent that performed the analysis")
    agent_name: str = Field(..., description="Name of the agent")
    findings: List[Finding] = Field(default_factory=list, description="List of findings")
    metrics: Dict[str, Any] = Field(
        default_factory=dict, description="Analysis metrics"
    )
    execution_time: float = Field(..., description="Analysis execution time in seconds")
    status: str = Field("completed", description="Analysis status")
    error: Optional[str] = Field(None, description="Error message if analysis failed")
    
    @validator("status")
    def validate_status(cls, v: str) -> str:
        """Validate analysis status."""
        valid_statuses = {"pending", "in_progress", "completed", "failed"}
        if v.lower() not in valid_statuses:
            raise ValueError(
                f"Status must be one of: {', '.join(valid_statuses)}"
            )
        return v.lower()


class ReportSummary(BaseCodeReviewModel):
    """Model representing a summary of the review report."""
    
    total_issues: int = Field(0, description="Total number of issues found")
    critical_issues: int = Field(0, description="Number of critical issues")
    high_issues: int = Field(0, description="Number of high severity issues")
    medium_issues: int = Field(0, description="Number of medium severity issues")
    low_issues: int = Field(0, description="Number of low severity issues")
    code_quality_score: float = Field(
        0.0, description="Overall code quality score (0-100)"
    )
    test_coverage_percentage: Optional[float] = Field(
        None, description="Test coverage percentage"
    )
    
    @validator("code_quality_score")
    def validate_code_quality_score(cls, v: float) -> float:
        """Validate code quality score."""
        if not 0 <= v <= 100:
            raise ValueError("Code quality score must be between 0 and 100")
        return v
    
    @validator("test_coverage_percentage")
    def validate_test_coverage(cls, v: Optional[float]) -> Optional[float]:
        """Validate test coverage percentage."""
        if v is not None and not 0 <= v <= 100:
            raise ValueError("Test coverage percentage must be between 0 and 100")
        return v


class ReviewMetrics(BaseCodeReviewModel):
    """Model representing metrics for a code review."""
    
    total_files: int = Field(0, description="Total number of files analyzed")
    total_lines: int = Field(0, description="Total number of lines analyzed")
    languages: Dict[str, int] = Field(
        default_factory=dict, description="Lines of code by language"
    )
    analysis_duration: float = Field(
        0.0, description="Total analysis duration in seconds"
    )
    agent_durations: Dict[str, float] = Field(
        default_factory=dict, description="Analysis duration by agent"
    )


class ReviewReport(BaseCodeReviewModel):
    """Model representing a complete code review report."""
    
    session_id: str = Field(..., description="Session ID of the review")
    summary: ReportSummary = Field(
        default_factory=ReportSummary, description="Report summary"
    )
    findings_by_category: Dict[str, List[Finding]] = Field(
        default_factory=dict, description="Findings grouped by category"
    )
    metrics: ReviewMetrics = Field(
        default_factory=ReviewMetrics, description="Review metrics"
    )
    recommendations: List[str] = Field(
        default_factory=list, description="Recommendations for improvement"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Report generation timestamp"
    )
    
    @validator("findings_by_category")
    def validate_findings_categories(cls, v: Dict[str, List[Finding]]) -> Dict[str, List[Finding]]:
        """Validate findings categories."""
        valid_categories = {"style", "security", "performance", "testing"}
        for category in v.keys():
            if category.lower() not in valid_categories:
                raise ValueError(
                    f"Category must be one of: {', '.join(valid_categories)}"
                )
        return v