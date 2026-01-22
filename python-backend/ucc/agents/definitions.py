"""Segment 2: Definitions Agent.

Extracts defined terms from policy documents, identifies mentions,
and produces definition-expanded text for downstream semantic alignment.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Set, Tuple

from ..io.pdf_blocks import Block
from ..storage.definitions_store import (
    BlockExpansion,
    Definition,
    DefinitionsResult,
    DefinitionsStore,
    DefinitionType,
    TermMention,
)
from ..storage.layout_store import LayoutStore


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Section path keywords that indicate a definitions zone
DEFINITION_ZONE_KEYWORDS = frozenset([
    "definition",
    "definitions",
    "glossary",
    "meaning of words",
    "interpretation",
    "what words mean",
    "key terms",
])

# Regex patterns for extracting definitions

# Glossary-style: "TERM" means ... or TERM means ...
GLOSSARY_QUOTED_PATTERN = re.compile(
    r'^["\u201c]([A-Za-z][A-Za-z0-9\s\-/&]+)["\u201d]\s+'
    r'(?:means?|refers?\s+to|is\s+defined\s+as|shall\s+mean)\s+(.+)',
    re.IGNORECASE | re.DOTALL,
)

# Glossary-style: TERM means ...
GLOSSARY_UNQUOTED_PATTERN = re.compile(
    r'^([A-Z][A-Za-z0-9\s\-/&]{1,50})\s+'
    r'(?:means?|refers?\s+to|is\s+defined\s+as)\s+(.+)',
    re.DOTALL,
)

# TERM: definition text
COLON_PATTERN = re.compile(
    r'^["\u201c]?([A-Z][A-Za-z0-9\s\-/&]{1,50})["\u201d]?\s*[:–—]\s*(.+)',
    re.DOTALL,
)

# Inline definition: "Term" means ... (mid-sentence)
INLINE_QUOTED_PATTERN = re.compile(
    r'["\u201c]([A-Za-z][A-Za-z0-9\s\-/&]+)["\u201d]\s+'
    r'(?:means?|refers?\s+to|is\s+defined\s+as|shall\s+mean)\s+([^.]+\.)',
    re.IGNORECASE,
)

# All-caps term detection for glossary
ALL_CAPS_TERM_PATTERN = re.compile(r'^([A-Z][A-Z\s\-/&]{2,50})$')

# Maximum definition text length for truncation in expansions
MAX_EXPANSION_DEF_LENGTH = 220

# Maximum expansion depth (how many levels of nested terms to expand)
MAX_EXPANSION_DEPTH = 1

# Maximum mentions per term per block to expand
MAX_MENTIONS_TO_EXPAND = 2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _canonicalize_term(term: str) -> str:
    """Normalize a term to a canonical key: uppercase, strip punctuation, collapse whitespace."""
    term = term.strip()
    term = re.sub(r'["\u201c\u201d\'`]', '', term)
    term = re.sub(r'[^\w\s]', ' ', term)
    term = re.sub(r'\s+', ' ', term)
    return term.upper().strip()


def _generate_id(*parts: str) -> str:
    """Generate a stable hash-based ID from parts."""
    combined = "|".join(parts)
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()[:16]


def _is_definition_zone(section_path: List[str]) -> bool:
    """Check if the section path indicates a definitions zone."""
    path_lower = " ".join(section_path).lower()
    return any(kw in path_lower for kw in DEFINITION_ZONE_KEYWORDS)


def _extract_context_snippet(text: str, start: int, end: int, context_chars: int = 40) -> str:
    """Extract a snippet of text around a match."""
    snippet_start = max(0, start - context_chars)
    snippet_end = min(len(text), end + context_chars)
    snippet = text[snippet_start:snippet_end]
    if snippet_start > 0:
        snippet = "..." + snippet
    if snippet_end < len(text):
        snippet = snippet + "..."
    return snippet


def _truncate_definition(text: str, max_length: int = MAX_EXPANSION_DEF_LENGTH) -> str:
    """Truncate definition text for expansion, preserving word boundaries."""
    text = text.strip()
    if len(text) <= max_length:
        return text
    truncated = text[:max_length].rsplit(' ', 1)[0]
    return truncated.rstrip('.,;:') + "..."


# ---------------------------------------------------------------------------
# Definition Extraction
# ---------------------------------------------------------------------------


@dataclass
class _RawDefinition:
    """Intermediate representation before deduplication."""
    term_surface: str
    definition_text: str
    source_block_id: str
    source_page: int
    confidence: float
    definition_type: DefinitionType


def _extract_glossary_definitions(block: Block, in_definition_zone: bool) -> List[_RawDefinition]:
    """Extract definitions using glossary-style patterns."""
    results: List[_RawDefinition] = []
    text = block.text.strip()
    
    # Try quoted pattern first (highest confidence)
    match = GLOSSARY_QUOTED_PATTERN.match(text)
    if match:
        term = match.group(1).strip()
        defn = match.group(2).strip()
        confidence = 0.95 if in_definition_zone else 0.75
        results.append(_RawDefinition(
            term_surface=term,
            definition_text=defn,
            source_block_id=block.id,
            source_page=block.page_number,
            confidence=confidence,
            definition_type=DefinitionType.GLOSSARY if in_definition_zone else DefinitionType.INLINE,
        ))
        return results
    
    # Try unquoted pattern
    match = GLOSSARY_UNQUOTED_PATTERN.match(text)
    if match:
        term = match.group(1).strip()
        defn = match.group(2).strip()
        # Lower confidence for unquoted
        confidence = 0.85 if in_definition_zone else 0.60
        results.append(_RawDefinition(
            term_surface=term,
            definition_text=defn,
            source_block_id=block.id,
            source_page=block.page_number,
            confidence=confidence,
            definition_type=DefinitionType.GLOSSARY if in_definition_zone else DefinitionType.INLINE,
        ))
        return results
    
    # Try colon pattern
    match = COLON_PATTERN.match(text)
    if match and in_definition_zone:
        term = match.group(1).strip()
        defn = match.group(2).strip()
        results.append(_RawDefinition(
            term_surface=term,
            definition_text=defn,
            source_block_id=block.id,
            source_page=block.page_number,
            confidence=0.80,
            definition_type=DefinitionType.GLOSSARY,
        ))
        return results
    
    return results


def _extract_inline_definitions(block: Block) -> List[_RawDefinition]:
    """Extract inline definitions from non-glossary blocks."""
    results: List[_RawDefinition] = []
    text = block.text
    
    for match in INLINE_QUOTED_PATTERN.finditer(text):
        term = match.group(1).strip()
        defn = match.group(2).strip()
        results.append(_RawDefinition(
            term_surface=term,
            definition_text=defn,
            source_block_id=block.id,
            source_page=block.page_number,
            confidence=0.70,
            definition_type=DefinitionType.INLINE,
        ))
    
    return results


def _extract_definitions_from_blocks(blocks: List[Block]) -> List[_RawDefinition]:
    """Extract all definitions from blocks."""
    raw_definitions: List[_RawDefinition] = []
    
    for block in blocks:
        if block.is_admin:
            continue
        
        in_definition_zone = _is_definition_zone(block.section_path)
        
        # Try glossary extraction first
        glossary_defs = _extract_glossary_definitions(block, in_definition_zone)
        if glossary_defs:
            raw_definitions.extend(glossary_defs)
            continue
        
        # Try inline extraction for non-glossary blocks
        if not in_definition_zone:
            inline_defs = _extract_inline_definitions(block)
            raw_definitions.extend(inline_defs)
    
    return raw_definitions


def _deduplicate_definitions(
    raw_definitions: List[_RawDefinition],
    doc_id: str,
) -> List[Definition]:
    """Deduplicate definitions by canonical term, keeping highest confidence."""
    
    by_canonical: Dict[str, _RawDefinition] = {}
    
    for raw in raw_definitions:
        canonical = _canonicalize_term(raw.term_surface)
        if not canonical or len(canonical) < 2:
            continue
        
        existing = by_canonical.get(canonical)
        if existing is None or raw.confidence > existing.confidence:
            by_canonical[canonical] = raw
    
    definitions: List[Definition] = []
    for canonical, raw in by_canonical.items():
        definition_id = _generate_id(doc_id, "def", canonical)
        definitions.append(Definition(
            definition_id=definition_id,
            doc_id=doc_id,
            term_canonical=canonical,
            term_surface=raw.term_surface,
            definition_text=raw.definition_text,
            source_block_id=raw.source_block_id,
            source_page=raw.source_page,
            confidence=raw.confidence,
            definition_type=raw.definition_type,
        ))
    
    return sorted(definitions, key=lambda d: d.term_canonical)


# ---------------------------------------------------------------------------
# Term Mentions
# ---------------------------------------------------------------------------


def _build_term_patterns(definitions: List[Definition]) -> Dict[str, re.Pattern[str]]:
    """Build word-boundary regex patterns for each defined term."""
    patterns: Dict[str, re.Pattern[str]] = {}
    
    for defn in definitions:
        # Use surface form for matching, case-insensitive
        term = defn.term_surface.strip()
        # Escape regex special chars
        escaped = re.escape(term)
        # Word boundary pattern
        pattern = re.compile(r'\b' + escaped + r'\b', re.IGNORECASE)
        patterns[defn.term_canonical] = pattern
    
    return patterns


def _find_mentions(
    blocks: List[Block],
    definitions: List[Definition],
    doc_id: str,
) -> List[TermMention]:
    """Find all mentions of defined terms in blocks."""
    
    if not definitions:
        return []
    
    patterns = _build_term_patterns(definitions)
    definition_block_ids = {d.source_block_id for d in definitions}
    
    mentions: List[TermMention] = []
    mention_counter = 0
    
    for block in blocks:
        # Skip admin blocks and definition source blocks
        if block.is_admin:
            continue
        if block.id in definition_block_ids:
            continue
        
        text = block.text
        
        for canonical, pattern in patterns.items():
            for match in pattern.finditer(text):
                mention_counter += 1
                mention_id = _generate_id(doc_id, "mention", str(mention_counter), block.id)
                snippet = _extract_context_snippet(text, match.start(), match.end())
                
                mentions.append(TermMention(
                    mention_id=mention_id,
                    doc_id=doc_id,
                    block_id=block.id,
                    term_canonical=canonical,
                    span_start=match.start(),
                    span_end=match.end(),
                    context_snippet=snippet,
                ))
    
    return mentions


# ---------------------------------------------------------------------------
# Block Expansion
# ---------------------------------------------------------------------------


@dataclass
class _DefinitionGraph:
    """Lightweight graph for term references."""
    term_to_definition: Dict[str, str] = field(default_factory=dict)
    term_references: Dict[str, Set[str]] = field(default_factory=dict)


def _build_definition_graph(definitions: List[Definition]) -> _DefinitionGraph:
    """Build a lightweight definition graph for expansion."""
    graph = _DefinitionGraph()
    
    # Build term -> definition mapping
    for defn in definitions:
        graph.term_to_definition[defn.term_canonical] = defn.definition_text
    
    # Find term references within definitions
    patterns = _build_term_patterns(definitions)
    
    for defn in definitions:
        refs: Set[str] = set()
        for canonical, pattern in patterns.items():
            if canonical == defn.term_canonical:
                continue  # Don't self-reference
            if pattern.search(defn.definition_text):
                refs.add(canonical)
        graph.term_references[defn.term_canonical] = refs
    
    return graph


def _expand_block_text(
    block: Block,
    definitions: List[Definition],
    mentions_in_block: List[TermMention],
    graph: _DefinitionGraph,
    max_depth: int = MAX_EXPANSION_DEPTH,
    max_def_length: int = MAX_EXPANSION_DEF_LENGTH,
    max_mentions_per_term: int = MAX_MENTIONS_TO_EXPAND,
) -> Tuple[str, Dict[str, Any]]:
    """
    Expand a block's text by appending definition expansions.
    
    Returns (expanded_text, expansion_meta).
    """
    
    if not mentions_in_block or not definitions:
        return block.text, {"terms_expanded": [], "depth": 0, "truncated": False}
    
    # Group mentions by canonical term
    mentions_by_term: Dict[str, List[TermMention]] = {}
    for mention in mentions_in_block:
        if mention.term_canonical not in mentions_by_term:
            mentions_by_term[mention.term_canonical] = []
        mentions_by_term[mention.term_canonical].append(mention)
    
    # Sort terms by first occurrence
    terms_order = sorted(
        mentions_by_term.keys(),
        key=lambda t: min(m.span_start for m in mentions_by_term[t])
    )
    
    # Build expansion appendix
    expansions: List[str] = []
    terms_expanded: List[str] = []
    total_expansion_length = 0
    truncated = False
    
    for canonical in terms_order:
        if canonical not in graph.term_to_definition:
            continue
        
        # Limit mentions per term
        term_mentions = mentions_by_term[canonical][:max_mentions_per_term]
        if not term_mentions:
            continue
        
        # Get definition text (truncated)
        full_def = graph.term_to_definition[canonical]
        truncated_def = _truncate_definition(full_def, max_def_length)
        was_truncated = len(truncated_def) < len(full_def)
        
        # Find original surface form
        surface_form = canonical  # fallback
        for defn in definitions:
            if defn.term_canonical == canonical:
                surface_form = defn.term_surface
                break
        
        expansion_entry = f"{surface_form} [defined as: {truncated_def}]"
        
        # Check if adding this would be too long (keep total expansion < 1000 chars)
        if total_expansion_length + len(expansion_entry) > 1000:
            truncated = True
            break
        
        expansions.append(expansion_entry)
        terms_expanded.append(canonical)
        total_expansion_length += len(expansion_entry)
        
        if was_truncated:
            truncated = True
    
    # Build final expanded text
    if expansions:
        expanded_text = block.text + " | " + " | ".join(expansions)
    else:
        expanded_text = block.text
    
    meta: Dict[str, Any] = {
        "terms_expanded": terms_expanded,
        "depth": 1 if terms_expanded else 0,
        "truncated": truncated,
        "expansion_count": len(expansions),
    }
    
    return expanded_text, meta


def _build_expansions(
    blocks: List[Block],
    definitions: List[Definition],
    mentions: List[TermMention],
    doc_id: str,
) -> List[BlockExpansion]:
    """Build expanded text for all blocks."""
    
    graph = _build_definition_graph(definitions)
    
    # Group mentions by block
    mentions_by_block: Dict[str, List[TermMention]] = {}
    for mention in mentions:
        if mention.block_id not in mentions_by_block:
            mentions_by_block[mention.block_id] = []
        mentions_by_block[mention.block_id].append(mention)
    
    expansions: List[BlockExpansion] = []
    
    for block in blocks:
        block_mentions = mentions_by_block.get(block.id, [])
        expanded_text, meta = _expand_block_text(
            block, definitions, block_mentions, graph
        )
        
        expansions.append(BlockExpansion(
            doc_id=doc_id,
            block_id=block.id,
            expanded_text=expanded_text,
            expansion_meta=meta,
        ))
    
    return expansions


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_definitions_agent(doc_id: str) -> DefinitionsResult:
    """
    Run the Definitions Agent on a previously processed document.
    
    Args:
        doc_id: Document ID from Segment 1 (Document Layout Agent).
    
    Returns:
        DefinitionsResult containing definitions, mentions, and expansions.
    
    Raises:
        ValueError: If no blocks found for doc_id.
    """
    
    # Load blocks from Segment 1 output
    layout_store = LayoutStore()
    blocks = layout_store.get_blocks(doc_id)
    
    if not blocks:
        raise ValueError(f"No blocks found for doc_id: {doc_id}")
    
    # Extract definitions
    raw_definitions = _extract_definitions_from_blocks(blocks)
    definitions = _deduplicate_definitions(raw_definitions, doc_id)
    
    # Find mentions
    mentions = _find_mentions(blocks, definitions, doc_id)
    
    # Build expansions
    expansions = _build_expansions(blocks, definitions, mentions, doc_id)
    
    # Persist results (idempotent)
    definitions_store = DefinitionsStore()
    definitions_store.clear_definitions(doc_id)
    definitions_store.persist_definitions(definitions)
    definitions_store.persist_mentions(mentions)
    definitions_store.persist_expansions(expansions)
    
    return DefinitionsResult(
        doc_id=doc_id,
        definitions=definitions,
        mentions=mentions,
        expansions=expansions,
    )


def get_definitions(doc_id: str) -> List[Definition]:
    """Retrieve persisted definitions for a document."""
    store = DefinitionsStore()
    return store.get_definitions(doc_id)


def get_expanded_block_text(doc_id: str, block_id: str) -> str | None:
    """Retrieve expanded text for a specific block."""
    store = DefinitionsStore()
    expansion = store.get_expansion(doc_id, block_id)
    if expansion:
        return expansion.expanded_text
    return None


def get_all_expanded_blocks(doc_id: str) -> List[BlockExpansion]:
    """Retrieve all expanded blocks for a document."""
    store = DefinitionsStore()
    return store.get_all_expansions(doc_id)


def get_term_mentions(doc_id: str, block_id: str | None = None) -> List[TermMention]:
    """Retrieve term mentions for a document, optionally filtered by block."""
    store = DefinitionsStore()
    return store.get_mentions(doc_id, block_id)
