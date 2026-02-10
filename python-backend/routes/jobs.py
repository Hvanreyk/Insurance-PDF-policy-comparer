"""FastAPI router for job management endpoints.

Provides endpoints for submitting comparison jobs, checking status,
retrieving results, and cancelling jobs.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Query
from pydantic import BaseModel, Field

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tasks.comparison_chain import (
    run_comparison_job,
    get_job_status,
    get_job_result,
    cancel_job,
)
from ucc.storage.job_store import JobStore, JobStatus
from ucc.delivery.service import DeliveryService


router = APIRouter(prefix="/jobs", tags=["jobs"])


# =============================================================================
# Request/Response Models
# =============================================================================


class JobSubmitResponse(BaseModel):
    """Response from job submission."""
    job_id: str
    celery_task_id: str
    status: str = "QUEUED"
    message: str = "Job submitted successfully"


class JobStatusResponse(BaseModel):
    """Response for job status query."""
    job_id: str
    doc_id_a: str
    doc_id_b: str
    file_name_a: Optional[str] = None
    file_name_b: Optional[str] = None
    status: str
    current_segment: int
    current_segment_name: str
    total_segments: int
    progress_pct: float
    error_message: Optional[str] = None
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class JobListResponse(BaseModel):
    """Response for job list query."""
    jobs: List[JobStatusResponse]
    total: int
    limit: int
    offset: int


class JobCancelResponse(BaseModel):
    """Response for job cancellation."""
    job_id: str
    cancelled: bool
    message: str


# =============================================================================
# Endpoints
# =============================================================================


@router.post("/compare", response_model=JobSubmitResponse)
async def submit_comparison_job(
    file_a: UploadFile = File(..., description="Policy document A (PDF)"),
    file_b: UploadFile = File(..., description="Policy document B (PDF)"),
    options: Optional[str] = Form(None, description="Optional comparison options JSON"),
) -> JobSubmitResponse:
    """Submit a new policy comparison job.
    
    Queues the comparison for async processing. Returns immediately with a
    job_id that can be used to track progress and retrieve results.
    
    The comparison will execute all 7 segments sequentially:
    - Segments 1-4: Document A preprocessing (layout, definitions, classification, DNA)
    - Segments 5-8: Document B preprocessing (layout, definitions, classification, DNA)
    - Segment 9: Semantic alignment
    - Segment 10: Delta interpretation
    - Segment 11: Narrative summarisation
    """
    # Validate file types
    if not file_a.filename or not file_a.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="file_a must be a PDF file")
    if not file_b.filename or not file_b.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="file_b must be a PDF file")
    
    # Read file contents
    try:
        contents_a = await file_a.read()
        contents_b = await file_b.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read uploaded files: {e}")
    
    if not contents_a:
        raise HTTPException(status_code=400, detail="file_a is empty")
    if not contents_b:
        raise HTTPException(status_code=400, detail="file_b is empty")
    
    # Submit job to queue
    try:
        job_id, celery_task_id = run_comparison_job(
            pdf_bytes_a=contents_a,
            pdf_bytes_b=contents_b,
            file_name_a=file_a.filename,
            file_name_b=file_b.filename,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue comparison job: {e}")
    
    return JobSubmitResponse(
        job_id=job_id,
        celery_task_id=celery_task_id,
        status="QUEUED",
        message="Job submitted successfully. Use GET /jobs/{job_id} to track progress.",
    )


@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_job(job_id: str) -> JobStatusResponse:
    """Get the current status and progress of a comparison job.
    
    Returns detailed progress information including:
    - Current segment being processed
    - Overall progress percentage
    - Status (QUEUED, RUNNING, COMPLETED, FAILED, CANCELLED)
    - Error message if failed
    """
    status = get_job_status(job_id)
    
    if "error" in status:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    
    return JobStatusResponse(**status)


@router.get("/{job_id}/result")
async def get_job_result_endpoint(job_id: str) -> Dict[str, Any]:
    """Get the full result of a completed comparison job.
    
    Returns the complete comparison result including:
    - Aligned clauses
    - Detected deltas
    - Narrative summary bullets
    - Statistics
    
    Returns 404 if job not found, 202 if still processing.
    """
    job_store = JobStore()
    job = job_store.get(job_id)
    
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    
    if job.status == JobStatus.FAILED:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Job failed",
                "error": job.error_message,
                "job_id": job_id,
            }
        )
    
    if job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=202,
            detail={
                "message": "Job still processing",
                "status": job.status.value,
                "progress_pct": job.progress_pct,
                "current_segment": job.current_segment,
                "job_id": job_id,
            }
        )
    
    # Always use the DeliveryService to assemble a properly shaped result
    # from the persisted segment outputs (matches the frontend UCCComparisonResult type).
    # The raw Celery task result stored in job_store has a different shape.
    try:
        delivery = DeliveryService()
        full_result = delivery.get_comparison_result(job.doc_id_a, job.doc_id_b)
        return full_result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve comparison result: {e}"
        )


@router.post("/{job_id}/cancel", response_model=JobCancelResponse)
async def cancel_job_endpoint(job_id: str) -> JobCancelResponse:
    """Cancel a running comparison job.
    
    Attempts to cancel the job if it's still in progress.
    Returns whether the cancellation was successful.
    """
    job_store = JobStore()
    job = job_store.get(job_id)
    
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    
    if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
        return JobCancelResponse(
            job_id=job_id,
            cancelled=False,
            message=f"Job already {job.status.value.lower()}, cannot cancel",
        )
    
    success = cancel_job(job_id)
    
    return JobCancelResponse(
        job_id=job_id,
        cancelled=success,
        message="Job cancelled successfully" if success else "Failed to cancel job",
    )


@router.get("", response_model=JobListResponse)
async def list_jobs(
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=100, description="Maximum results to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
) -> JobListResponse:
    """List comparison jobs with optional filtering.
    
    Returns a paginated list of jobs, optionally filtered by status.
    """
    job_store = JobStore()
    
    # Validate status if provided
    status_filter = None
    if status:
        try:
            status_filter = JobStatus(status.upper())
        except ValueError:
            valid_statuses = [s.value for s in JobStatus]
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status '{status}'. Valid values: {valid_statuses}"
            )
    
    jobs = job_store.list_jobs(status=status_filter, limit=limit, offset=offset)
    
    return JobListResponse(
        jobs=[JobStatusResponse(**job.to_dict()) for job in jobs],
        total=len(jobs),
        limit=limit,
        offset=offset,
    )


@router.delete("/{job_id}")
async def delete_job(job_id: str) -> Dict[str, Any]:
    """Delete a job record.
    
    Only allows deletion of completed, failed, or cancelled jobs.
    """
    job_store = JobStore()
    job = job_store.get(job_id)
    
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    
    if job.status in (JobStatus.PENDING, JobStatus.QUEUED, JobStatus.RUNNING):
        raise HTTPException(
            status_code=400,
            detail="Cannot delete a job that is still processing. Cancel it first.",
        )
    
    success = job_store.delete(job_id)
    
    return {
        "job_id": job_id,
        "deleted": success,
        "message": "Job deleted successfully" if success else "Failed to delete job",
    }
