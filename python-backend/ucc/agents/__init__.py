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
]
