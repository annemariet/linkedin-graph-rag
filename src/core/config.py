"""
Configuration management for Code Review Assistant.
"""

from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )
    
    # Application settings
    DEBUG: bool = Field(default=False, description="Debug mode")
    HOST: str = Field(default="0.0.0.0", description="Host to bind to")
    PORT: int = Field(default=8000, description="Port to bind to")
    ALLOWED_HOSTS: List[str] = Field(
        default=["*"], description="Allowed CORS origins"
    )
    
    # Database settings
    DATABASE_URL: str = Field(
        default="postgresql://user:password@localhost:5432/code_review_db",
        description="Database connection URL"
    )
    
    # Redis settings
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL"
    )
    
    # Celery settings
    CELERY_BROKER_URL: str = Field(
        default="redis://localhost:6379/1",
        description="Celery broker URL"
    )
    CELERY_RESULT_BACKEND: str = Field(
        default="redis://localhost:6379/2",
        description="Celery result backend URL"
    )
    
    # LLM settings
    OPENAI_API_KEY: str = Field(
        default="", description="OpenAI API key"
    )
    OPENAI_MODEL: str = Field(
        default="gpt-4", description="OpenAI model to use"
    )
    
    # CrewAI settings
    CREWAI_LOG_LEVEL: str = Field(
        default="INFO", description="CrewAI log level"
    )
    
    # Analysis settings
    MAX_FILE_SIZE_MB: int = Field(
        default=10, description="Maximum file size in MB"
    )
    ANALYSIS_TIMEOUT_SECONDS: int = Field(
        default=300, description="Analysis timeout in seconds"
    )
    
    # Security settings
    SECRET_KEY: str = Field(
        default="your-secret-key-change-in-production",
        description="Secret key for session management"
    )


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()