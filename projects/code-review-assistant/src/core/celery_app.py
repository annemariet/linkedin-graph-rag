"""
Celery application configuration for asynchronous task processing.
"""

from celery import Celery

from src.core.config import get_settings

settings = get_settings()

# Create Celery app
celery_app = Celery(
    "code_review_assistant",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

# Configure Celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_time_limit=settings.ANALYSIS_TIMEOUT_SECONDS,
)

# Include task modules
celery_app.autodiscover_tasks(["src.core.tasks"])