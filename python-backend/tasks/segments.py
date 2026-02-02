"""Individual segment tasks for the UCC pipeline.

Each segment is a Celery task that can be chained together for
sequential execution with progress tracking.

PDF files are loaded from disk storage using doc_ids, not passed through
the Celery message queue.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded

from tasks.callbacks import update_job_progress, on_task_retry
from ucc.storage.job_store import JobStatus, SEGMENT_NAMES
from ucc.storage.pdf_store import load_pdf


# Common task decorator with retry configuration
TASK_CONFIG = {
    "bind": True,
    "max_retries": 3,
    "default_retry_delay": 30,
    "autoretry_for": (ConnectionError, TimeoutError),
    "retry_backoff": True,
    "retry_backoff_max": 120,
    "retry_jitter": True,
}


def _handle_task_error(task, job_id: str, segment: int, exc: Exception):
    """Handle task errors with retry logic."""
    if task.request.retries < task.max_retries:
        on_task_retry(job_id, exc, task.request.retries + 1)
        raise task.retry(exc=exc)
    else:
        update_job_progress(
            job_id,
            segment=segment,
            status=JobStatus.FAILED,
            error_message=f"Max retries exceeded: {str(exc)}",
        )
        raise exc


# =============================================================================
# Document A/B Preprocessing Tasks (Segments 1-4)
# =============================================================================


@shared_task(**TASK_CONFIG)
def segment_1_document_layout(
    self,
    job_id: str,
    doc_id: str,
    doc_label: str,
) -> Dict[str, Any]:
    """Segment 1: Document Layout Analysis.
    
    Parses PDF, extracts blocks, removes furniture, applies sections.
    PDF is loaded from disk storage using doc_id.
    
    Args:
        job_id: Job identifier
        doc_id: Document identifier (used to load PDF from storage)
        doc_label: "A" or "B" for progress display
        
    Returns:
        Dict with doc_id for chaining
    """
    segment = 1 if doc_label == "A" else 5
    segment_name = SEGMENT_NAMES.get(segment, f"Document {doc_label}: Layout Analysis")
    
    try:
        update_job_progress(job_id, segment, JobStatus.RUNNING, segment_name=segment_name)
        
        # Load PDF from disk storage
        print(f"[{job_id}] Loading PDF for doc_id: {doc_id}")
        pdf_bytes = load_pdf(doc_id)
        print(f"[{job_id}] Loaded PDF ({len(pdf_bytes)} bytes)")
        
        # Import and run the agent
        from ucc.agents.document_layout import run_document_layout
        
        result = run_document_layout(pdf_bytes, doc_id=doc_id)
        
        print(f"[{job_id}] Document layout complete: {len(result.blocks)} blocks")
        
        return {
            "job_id": job_id,
            "doc_id": doc_id,
            "doc_label": doc_label,
            "segment": segment,
            "block_count": len(result.blocks),
        }
        
    except SoftTimeLimitExceeded:
        update_job_progress(
            job_id, segment, JobStatus.FAILED,
            error_message=f"Document {doc_label} layout analysis timed out"
        )
        raise
    except FileNotFoundError as exc:
        update_job_progress(
            job_id, segment, JobStatus.FAILED,
            error_message=f"PDF file not found for doc_id: {doc_id}"
        )
        raise exc
    except Exception as exc:
        _handle_task_error(self, job_id, segment, exc)


@shared_task(**TASK_CONFIG)
def segment_2_definitions(
    self,
    prev_result: Dict[str, Any],
) -> Dict[str, Any]:
    """Segment 2: Definitions Extraction.
    
    Extracts defined terms and expands block text with definitions.
    
    Args:
        prev_result: Result from segment 1
        
    Returns:
        Dict with doc_id for chaining
    """
    job_id = prev_result["job_id"]
    doc_id = prev_result["doc_id"]
    doc_label = prev_result["doc_label"]
    segment = 2 if doc_label == "A" else 6
    segment_name = SEGMENT_NAMES.get(segment, f"Document {doc_label}: Definitions")
    
    try:
        update_job_progress(job_id, segment, JobStatus.RUNNING, segment_name=segment_name)
        
        from ucc.agents.definitions import run_definitions_agent, get_definitions
        
        run_definitions_agent(doc_id)
        definitions = get_definitions(doc_id)
        
        print(f"[{job_id}] Definitions complete: {len(definitions)} definitions")
        
        return {
            **prev_result,
            "segment": segment,
            "definition_count": len(definitions),
        }
        
    except SoftTimeLimitExceeded:
        update_job_progress(
            job_id, segment, JobStatus.FAILED,
            error_message=f"Document {doc_label} definitions extraction timed out"
        )
        raise
    except Exception as exc:
        _handle_task_error(self, job_id, segment, exc)


@shared_task(**TASK_CONFIG)
def segment_3_classification(
    self,
    prev_result: Dict[str, Any],
) -> Dict[str, Any]:
    """Segment 3: Clause Classification.
    
    Classifies each block by clause type (EXCLUSION, CONDITION, etc).
    
    Args:
        prev_result: Result from segment 2
        
    Returns:
        Dict with doc_id for chaining
    """
    job_id = prev_result["job_id"]
    doc_id = prev_result["doc_id"]
    doc_label = prev_result["doc_label"]
    segment = 3 if doc_label == "A" else 7
    segment_name = SEGMENT_NAMES.get(segment, f"Document {doc_label}: Classification")
    
    try:
        update_job_progress(job_id, segment, JobStatus.RUNNING, segment_name=segment_name)
        
        from ucc.agents.clause_classification import run_clause_classification, get_all_classifications
        
        run_clause_classification(doc_id)
        classifications = get_all_classifications(doc_id)
        
        print(f"[{job_id}] Classification complete: {len(classifications)} classifications")
        
        return {
            **prev_result,
            "segment": segment,
            "classification_count": len(classifications),
        }
        
    except SoftTimeLimitExceeded:
        update_job_progress(
            job_id, segment, JobStatus.FAILED,
            error_message=f"Document {doc_label} classification timed out"
        )
        raise
    except Exception as exc:
        _handle_task_error(self, job_id, segment, exc)


@shared_task(**TASK_CONFIG)
def segment_4_clause_dna(
    self,
    prev_result: Dict[str, Any],
) -> Dict[str, Any]:
    """Segment 4: Clause DNA Extraction.
    
    Extracts structural DNA from each clause (polarity, strictness, etc).
    
    Args:
        prev_result: Result from segment 3
        
    Returns:
        Dict with doc_id for chaining
    """
    job_id = prev_result["job_id"]
    doc_id = prev_result["doc_id"]
    doc_label = prev_result["doc_label"]
    segment = 4 if doc_label == "A" else 8
    segment_name = SEGMENT_NAMES.get(segment, f"Document {doc_label}: Clause DNA")
    
    try:
        update_job_progress(job_id, segment, JobStatus.RUNNING, segment_name=segment_name)
        
        from ucc.agents.clause_dna import run_clause_dna_agent, get_all_dna
        
        run_clause_dna_agent(doc_id)
        dna_records = get_all_dna(doc_id)
        
        print(f"[{job_id}] Clause DNA complete: {len(dna_records)} DNA records")
        
        return {
            **prev_result,
            "segment": segment,
            "dna_count": len(dna_records),
        }
        
    except SoftTimeLimitExceeded:
        update_job_progress(
            job_id, segment, JobStatus.FAILED,
            error_message=f"Document {doc_label} DNA extraction timed out"
        )
        raise
    except Exception as exc:
        _handle_task_error(self, job_id, segment, exc)


# =============================================================================
# Comparison Tasks (Segments 5-7)
# =============================================================================


@shared_task(**TASK_CONFIG)
def segment_5_semantic_alignment(
    self,
    prev_result: Dict[str, Any],
    doc_id_a: str,
    doc_id_b: str,
) -> Dict[str, Any]:
    """Segment 5: Semantic Alignment.
    
    Aligns like-to-like clauses across both documents.
    
    Args:
        prev_result: Result from document B segment 4
        doc_id_a: Document A identifier
        doc_id_b: Document B identifier
        
    Returns:
        Dict with alignment results for chaining
    """
    job_id = prev_result["job_id"]
    segment = 9
    segment_name = SEGMENT_NAMES.get(segment, "Semantic Alignment")
    
    try:
        update_job_progress(job_id, segment, JobStatus.RUNNING, segment_name=segment_name)
        
        from ucc.agents.semantic_alignment import run_semantic_alignment
        
        result = run_semantic_alignment(doc_id_a, doc_id_b)
        
        print(f"[{job_id}] Semantic alignment complete: {len(result.alignments)} alignments")
        
        return {
            "job_id": job_id,
            "doc_id_a": doc_id_a,
            "doc_id_b": doc_id_b,
            "segment": segment,
            "alignment_count": len(result.alignments),
            "stats": result.stats,
        }
        
    except SoftTimeLimitExceeded:
        update_job_progress(
            job_id, segment, JobStatus.FAILED,
            error_message="Semantic alignment timed out"
        )
        raise
    except Exception as exc:
        _handle_task_error(self, job_id, segment, exc)


@shared_task(**TASK_CONFIG)
def segment_6_delta_interpretation(
    self,
    prev_result: Dict[str, Any],
) -> Dict[str, Any]:
    """Segment 6: Delta Interpretation.
    
    Detects and interprets changes between aligned clauses.
    
    Args:
        prev_result: Result from segment 5
        
    Returns:
        Dict with delta results for chaining
    """
    job_id = prev_result["job_id"]
    doc_id_a = prev_result["doc_id_a"]
    doc_id_b = prev_result["doc_id_b"]
    segment = 10
    segment_name = SEGMENT_NAMES.get(segment, "Delta Interpretation")
    
    try:
        update_job_progress(job_id, segment, JobStatus.RUNNING, segment_name=segment_name)
        
        from ucc.agents.delta_interpretation import run_delta_interpretation
        
        result = run_delta_interpretation(doc_id_a, doc_id_b)
        
        print(f"[{job_id}] Delta interpretation complete: {len(result.deltas)} deltas")
        
        return {
            **prev_result,
            "segment": segment,
            "delta_count": len(result.deltas),
            "delta_stats": result.stats,
        }
        
    except SoftTimeLimitExceeded:
        update_job_progress(
            job_id, segment, JobStatus.FAILED,
            error_message="Delta interpretation timed out"
        )
        raise
    except Exception as exc:
        _handle_task_error(self, job_id, segment, exc)


@shared_task(**TASK_CONFIG)
def segment_7_narrative_summary(
    self,
    prev_result: Dict[str, Any],
) -> Dict[str, Any]:
    """Segment 7: Narrative Summarisation.
    
    Generates human-readable summary bullets from deltas.
    
    Args:
        prev_result: Result from segment 6
        
    Returns:
        Final result dict with all comparison data
    """
    job_id = prev_result["job_id"]
    doc_id_a = prev_result["doc_id_a"]
    doc_id_b = prev_result["doc_id_b"]
    segment = 11
    segment_name = SEGMENT_NAMES.get(segment, "Narrative Summarisation")
    
    try:
        update_job_progress(job_id, segment, JobStatus.RUNNING, segment_name=segment_name)
        
        from ucc.agents.narrative_summarisation import run_narrative_summarisation
        
        result = run_narrative_summarisation(doc_id_a, doc_id_b)
        
        print(f"[{job_id}] Narrative summary complete: {len(result.bullets)} bullets")
        
        # Build final result
        final_result = {
            "job_id": job_id,
            "doc_id_a": doc_id_a,
            "doc_id_b": doc_id_b,
            "segment": segment,
            "summary": {
                "bullet_count": len(result.bullets),
                "confidence": result.confidence,
                "counts": {
                    "matched_clauses": result.counts.matched_clauses,
                    "unmatched_clauses": result.counts.unmatched_clauses,
                    "review_needed": result.counts.review_needed,
                    "total_bullets": result.counts.total_bullets,
                    "deltas_by_type": result.counts.deltas_by_type,
                },
            },
            "alignment_stats": prev_result.get("stats", {}),
            "delta_stats": prev_result.get("delta_stats", {}),
        }
        
        # Mark job as complete
        update_job_progress(
            job_id,
            segment=11,
            status=JobStatus.COMPLETED,
            segment_name="Complete",
            result_data=final_result,
        )
        
        print(f"[{job_id}] Job completed successfully!")
        
        return final_result
        
    except SoftTimeLimitExceeded:
        update_job_progress(
            job_id, segment, JobStatus.FAILED,
            error_message="Narrative summarisation timed out"
        )
        raise
    except Exception as exc:
        _handle_task_error(self, job_id, segment, exc)
