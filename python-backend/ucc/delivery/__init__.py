"""Segment 8: UI/API Delivery Layer."""

from .bands import SimilarityBand, get_similarity_band, SIMILARITY_BANDS
from .service import (
    list_policies,
    get_policy_sections,
    get_section_detail,
    get_clause_pair,
    get_similarity_summary,
    register_policy,
)

__all__ = [
    # Bands
    "SimilarityBand",
    "get_similarity_band",
    "SIMILARITY_BANDS",
    # Service
    "list_policies",
    "get_policy_sections",
    "get_section_detail",
    "get_clause_pair",
    "get_similarity_summary",
    "register_policy",
]
