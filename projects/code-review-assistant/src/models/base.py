"""
Base models for Code Review Assistant.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, validator


class BaseCodeReviewModel(BaseModel):
    """Base model for all Code Review Assistant models."""
    
    class Config:
        """Pydantic model configuration."""
        
        arbitrary_types_allowed = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }