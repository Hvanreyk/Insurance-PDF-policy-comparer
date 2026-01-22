"""Agents orchestrating pipeline segments."""

from .document_layout import (
    LayoutResult,
    doc_id_from_pdf,
    get_layout_blocks,
    run_document_layout,
)
from .definitions import (
    DefinitionsResult,
    get_all_expanded_blocks,
    get_definitions,
    get_expanded_block_text,
    get_term_mentions,
    run_definitions_agent,
)
from .clause_classification import (
    ClassificationResult,
    get_all_classifications,
    get_blocks_by_clause_type,
    get_classification,
    run_clause_classification,
)
from .clause_dna import (
    ClauseDNAResult,
    get_all_dna,
    get_clause_dna,
    get_dna_by_type,
    run_clause_dna_agent,
)
from .semantic_alignment import (
    AlignmentResult,
    get_alignment,
    get_alignments,
    run_semantic_alignment,
)

__all__ = [
    # Document Layout (Segment 1)
    "LayoutResult",
    "doc_id_from_pdf",
    "get_layout_blocks",
    "run_document_layout",
    # Definitions (Segment 2)
    "DefinitionsResult",
    "get_all_expanded_blocks",
    "get_definitions",
    "get_expanded_block_text",
    "get_term_mentions",
    "run_definitions_agent",
    # Clause Classification (Segment 3)
    "ClassificationResult",
    "get_all_classifications",
    "get_blocks_by_clause_type",
    "get_classification",
    "run_clause_classification",
    # Clause DNA (Segment 4)
    "ClauseDNAResult",
    "get_all_dna",
    "get_clause_dna",
    "get_dna_by_type",
    "run_clause_dna_agent",
    # Semantic Alignment (Segment 5)
    "AlignmentResult",
    "get_alignment",
    "get_alignments",
    "run_semantic_alignment",
]
