"""Celery chain orchestration for the full comparison workflow.

Builds and executes the sequential task chain for comparing two policy documents
through all 7 segments (11 steps total: 4 per doc + 3 comparison).
"""

from __future__ import annotations

import sys
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, Tuple
from uuid import uuid4

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from celery import chain, chord, group
from celery.result import AsyncResult

from tasks.segments import (
    segment_1_document_layout,
    segment_2_definitions,
    segment_3_classification,
    segment_4_clause_dna,
    segment_5_semantic_alignment,
    segment_6_delta_interpretation,
    segment_7_narrative_summary,
)
from tasks.callbacks import update_job_progress
from ucc.storage.job_store import JobStore, JobStatus


def _generate_doc_id(pdf_bytes: bytes) -> str:
    """Generate a stable document ID from PDF bytes."""
    return sha256(pdf_bytes).hexdigest()


def _generate_job_id() -> str:
    """Generate a unique job ID."""
    return str(uuid4())


def build_document_chain(
    job_id: str,
    doc_id: str,
    doc_label: str,
    pdf_bytes_hex: str,
):
    """Build the task chain for preprocessing a single document (Segments 1-4).
    
    Args:
        job_id: Job identifier
        doc_id: Document identifier
        doc_label: "A" or "B"
        pdf_bytes_hex: PDF bytes as hex string
        
    Returns:
        Celery chain for document preprocessing
    """
    return chain(
        segment_1_document_layout.s(job_id, doc_id, doc_label, pdf_bytes_hex),
        segment_2_definitions.s(),
        segment_3_classification.s(),
        segment_4_clause_dna.s(),
    )


def build_comparison_chain(
    job_id: str,
    doc_id_a: str,
    doc_id_b: str,
    pdf_bytes_a_hex: str,
    pdf_bytes_b_hex: str,
):
    """Build the complete comparison task chain (all 11 steps).
    
    The chain executes:
    1. Document A preprocessing (Segments 1-4)
    2. Document B preprocessing (Segments 5-8 in our numbering)
    3. Comparison stages (Segments 9-11)
    
    Args:
        job_id: Job identifier
        doc_id_a: Document A identifier
        doc_id_b: Document B identifier
        pdf_bytes_a_hex: PDF A bytes as hex string
        pdf_bytes_b_hex: PDF B bytes as hex string
        
    Returns:
        Celery chain for full comparison
    """
    # Build document A chain (segments 1-4)
    doc_a_chain = build_document_chain(job_id, doc_id_a, "A", pdf_bytes_a_hex)
    
    # Build document B chain (segments 5-8)
    doc_b_chain = build_document_chain(job_id, doc_id_b, "B", pdf_bytes_b_hex)
    
    # Build comparison chain (segments 9-11)
    comparison_chain = chain(
        segment_5_semantic_alignment.s(doc_id_a, doc_id_b),
        segment_6_delta_interpretation.s(),
        segment_7_narrative_summary.s(),
    )
    
    # Chain everything together: A -> B -> Comparison
    return chain(
        doc_a_chain,
        doc_b_chain,
        comparison_chain,
    )


def run_comparison_job(
    pdf_bytes_a: bytes,
    pdf_bytes_b: bytes,
    *,
    file_name_a: str | None = None,
    file_name_b: str | None = None,
    job_id: str | None = None,
) -> Tuple[str, str]:
    """Submit a comparison job to the Celery task queue.
    
    Args:
        pdf_bytes_a: PDF bytes for document A
        pdf_bytes_b: PDF bytes for document B
        file_name_a: Optional filename for document A
        file_name_b: Optional filename for document B
        job_id: Optional pre-generated job ID
        
    Returns:
        Tuple of (job_id, celery_task_id)
    """
    # Generate IDs
    if job_id is None:
        job_id = _generate_job_id()
    
    doc_id_a = _generate_doc_id(pdf_bytes_a)
    doc_id_b = _generate_doc_id(pdf_bytes_b)
    
    # Convert bytes to hex strings for JSON serialization
    pdf_bytes_a_hex = pdf_bytes_a.hex()
    pdf_bytes_b_hex = pdf_bytes_b.hex()
    
    # Create job record
    job_store = JobStore()
    job_store.create(
        job_id=job_id,
        doc_id_a=doc_id_a,
        doc_id_b=doc_id_b,
        file_name_a=file_name_a,
        file_name_b=file_name_b,
    )
    
    # Update status to queued
    update_job_progress(job_id, segment=0, status=JobStatus.QUEUED)
    
    # Build and submit the chain
    comparison_workflow = build_comparison_chain(
        job_id=job_id,
        doc_id_a=doc_id_a,
        doc_id_b=doc_id_b,
        pdf_bytes_a_hex=pdf_bytes_a_hex,
        pdf_bytes_b_hex=pdf_bytes_b_hex,
    )
    
    # Apply the chain (submit to queue)
    result = comparison_workflow.apply_async()
    
    # Update job with Celery task ID
    job_store.update(job_id, celery_task_id=result.id)
    
    return job_id, result.id


def get_job_status(job_id: str) -> Dict[str, Any]:
    """Get the current status of a comparison job.
    
    Args:
        job_id: Job identifier
        
    Returns:
        Job status dict
    """
    job_store = JobStore()
    job = job_store.get(job_id)
    
    if job is None:
        return {"error": "Job not found", "job_id": job_id}
    
    return job.to_dict()


def cancel_job(job_id: str) -> bool:
    """Cancel a running comparison job.
    
    Args:
        job_id: Job identifier
        
    Returns:
        True if cancelled successfully
    """
    job_store = JobStore()
    job = job_store.get(job_id)
    
    if job is None:
        return False
    
    # Only cancel if not already completed
    if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
        return False
    
    # Revoke the Celery task
    if job.celery_task_id:
        result = AsyncResult(job.celery_task_id)
        result.revoke(terminate=True)
    
    # Update job status
    update_job_progress(job_id, segment=job.current_segment, status=JobStatus.CANCELLED)
    
    return True


def get_job_result(job_id: str) -> Dict[str, Any] | None:
    """Get the result of a completed comparison job.
    
    Args:
        job_id: Job identifier
        
    Returns:
        Result data or None if not completed
    """
    job_store = JobStore()
    return job_store.get_result(job_id)
