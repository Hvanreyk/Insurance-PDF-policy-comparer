"""Progress callbacks and Redis pubsub for real-time updates.

Handles job progress updates to both SQLite (persistence) and Redis (real-time).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import redis

# Add parent directory to path for imports
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ucc.storage.job_store import JobStore, JobStatus, SEGMENT_NAMES


# Redis client for pubsub
_redis_client: Optional[redis.Redis] = None


def get_redis_client() -> redis.Redis:
    """Get or create Redis client for pubsub."""
    global _redis_client
    if _redis_client is None:
        redis_url = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
        _redis_client = redis.from_url(redis_url)
    return _redis_client


def publish_progress(job_id: str, data: Dict[str, Any]) -> None:
    """Publish progress update to Redis pubsub channel.
    
    Args:
        job_id: The job identifier
        data: Progress data to publish
    """
    try:
        client = get_redis_client()
        channel = f"job:{job_id}"
        client.publish(channel, json.dumps(data))
    except Exception as e:
        # Don't fail task if Redis pubsub fails
        print(f"Warning: Failed to publish progress to Redis: {e}")


def update_job_progress(
    job_id: str,
    segment: int,
    status: str | JobStatus,
    *,
    segment_name: str | None = None,
    error_message: str | None = None,
    result_data: Dict[str, Any] | None = None,
) -> None:
    """Update job progress in both SQLite and Redis.
    
    Args:
        job_id: The job identifier
        segment: Current segment number (0-11)
        status: Job status (RUNNING, COMPLETED, FAILED, etc.)
        segment_name: Optional segment name override
        error_message: Error message if failed
        result_data: Final result data if completed
    """
    job_store = JobStore()
    
    # Calculate progress percentage
    progress_pct = (segment / 11) * 100
    
    # Get segment name
    if segment_name is None:
        segment_name = SEGMENT_NAMES.get(segment, f"Segment {segment}")
    
    # Convert status to string if needed
    status_str = status.value if isinstance(status, JobStatus) else status
    
    # Prepare timestamps
    now = datetime.now(timezone.utc).isoformat()
    started_at = now if segment == 1 and status_str == "RUNNING" else None
    completed_at = now if status_str in ("COMPLETED", "FAILED", "CANCELLED") else None
    
    # Update SQLite
    job_store.update(
        job_id,
        status=status_str,
        current_segment=segment,
        current_segment_name=segment_name,
        progress_pct=progress_pct,
        error_message=error_message,
        result_data=result_data,
        started_at=started_at,
        completed_at=completed_at,
    )
    
    # Publish to Redis for real-time updates
    publish_progress(job_id, {
        "job_id": job_id,
        "segment": segment,
        "segment_name": segment_name,
        "progress_pct": round(progress_pct, 1),
        "status": status_str,
        "error_message": error_message,
        "timestamp": now,
    })


def on_task_success(job_id: str, result: Dict[str, Any]) -> None:
    """Callback when a task chain completes successfully.
    
    Args:
        job_id: The job identifier
        result: The final result data
    """
    update_job_progress(
        job_id,
        segment=11,
        status=JobStatus.COMPLETED,
        segment_name="Complete",
        result_data=result,
    )


def on_task_failure(job_id: str, error: Exception) -> None:
    """Callback when a task fails.
    
    Args:
        job_id: The job identifier
        error: The exception that occurred
    """
    job_store = JobStore()
    job = job_store.get(job_id)
    
    current_segment = job.current_segment if job else 0
    
    update_job_progress(
        job_id,
        segment=current_segment,
        status=JobStatus.FAILED,
        error_message=str(error),
    )


def on_task_retry(job_id: str, error: Exception, retry_count: int) -> None:
    """Callback when a task is being retried.
    
    Args:
        job_id: The job identifier
        error: The exception that caused the retry
        retry_count: Current retry attempt number
    """
    job_store = JobStore()
    job = job_store.get(job_id)
    
    current_segment = job.current_segment if job else 0
    segment_name = SEGMENT_NAMES.get(current_segment, f"Segment {current_segment}")
    
    update_job_progress(
        job_id,
        segment=current_segment,
        status=JobStatus.RETRYING,
        segment_name=f"{segment_name} (Retry {retry_count})",
    )
