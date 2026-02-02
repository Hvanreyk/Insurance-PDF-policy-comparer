"""Celery tasks package for UCC pipeline."""

from .callbacks import update_job_progress, publish_progress
from .segments import (
    segment_1_document_layout,
    segment_2_definitions,
    segment_3_classification,
    segment_4_clause_dna,
    segment_5_semantic_alignment,
    segment_6_delta_interpretation,
    segment_7_narrative_summary,
)
from .comparison_chain import build_comparison_chain, run_comparison_job

__all__ = [
    "update_job_progress",
    "publish_progress",
    "segment_1_document_layout",
    "segment_2_definitions",
    "segment_3_classification",
    "segment_4_clause_dna",
    "segment_5_semantic_alignment",
    "segment_6_delta_interpretation",
    "segment_7_narrative_summary",
    "build_comparison_chain",
    "run_comparison_job",
]
