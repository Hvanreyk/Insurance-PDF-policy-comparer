"""Celery application configuration for UCC pipeline.

This module configures Celery with Redis as the broker and result backend,
optimized for sequential document processing tasks.
"""

from __future__ import annotations

import os

from celery import Celery
from kombu import Queue

# Redis configuration from environment or defaults
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

# Create the Celery application
app = Celery(
    "ucc_pipeline",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=[
        "tasks.segments",
        "tasks.comparison_chain",
        "tasks.callbacks",
    ],
)

# Celery configuration
app.conf.update(
    # Serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    
    # Task tracking
    task_track_started=True,
    result_extended=True,
    
    # Timeouts (per segment)
    task_time_limit=600,  # 10 min hard limit
    task_soft_time_limit=540,  # 9 min soft limit
    
    # Worker configuration for sequential processing
    worker_prefetch_multiplier=1,  # Process one task at a time
    worker_concurrency=2,  # 2 concurrent workers (for parallel chains)
    
    # Reliability settings
    task_acks_late=True,  # Acknowledge after completion
    task_reject_on_worker_lost=True,  # Retry if worker dies
    
    # Result expiration (24 hours)
    result_expires=86400,
    
    # Task queues
    task_queues=[
        Queue("default", routing_key="default"),
        Queue("segments", routing_key="segments"),
        Queue("dlq", routing_key="dlq"),  # Dead letter queue
    ],
    task_default_queue="default",
    
    # Task routing
    task_routes={
        "tasks.segments.*": {"queue": "segments"},
        "tasks.comparison_chain.*": {"queue": "default"},
    },
    
    # Timezone
    timezone="UTC",
    enable_utc=True,
)


# Optional: Configure Celery beat for scheduled tasks (future use)
app.conf.beat_schedule = {}


if __name__ == "__main__":
    app.start()
