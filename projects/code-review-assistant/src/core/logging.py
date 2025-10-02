"""
Logging configuration for Code Review Assistant.
"""

import logging
import logging.config
import sys
from typing import Dict, Any

from src.core.config import get_settings

settings = get_settings()


def get_logging_config() -> Dict[str, Any]:
    """Get logging configuration dictionary."""
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            "detailed": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(funcName)s:%(lineno)d - %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": "DEBUG" if settings.DEBUG else "INFO",
                "formatter": "detailed" if settings.DEBUG else "default",
                "stream": sys.stdout,
            },
        },
        "loggers": {
            "src": {
                "level": "DEBUG" if settings.DEBUG else "INFO",
                "handlers": ["console"],
                "propagate": False,
            },
            "crewai": {
                "level": settings.CREWAI_LOG_LEVEL,
                "handlers": ["console"],
                "propagate": False,
            },
            "celery": {
                "level": "INFO",
                "handlers": ["console"],
                "propagate": False,
            },
        },
        "root": {
            "level": "INFO",
            "handlers": ["console"],
        },
    }


def setup_logging() -> None:
    """Setup logging configuration."""
    config = get_logging_config()
    logging.config.dictConfig(config)
    
    # Set up logger for the application
    logger = logging.getLogger("src")
    logger.info("Logging configuration initialized")