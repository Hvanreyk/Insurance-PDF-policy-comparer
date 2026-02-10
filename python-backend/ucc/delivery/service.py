"""Service layer for Segment 8: UI/API Delivery.

Queries persisted outputs from Segments 1-7 and shapes data for frontend.
Does NOT re-run parsing, embeddings, alignment, or deltas.
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..storage.layout_store import LayoutStore, _default_db_path, _ensure_parent
from ..storage.alignment_store import AlignmentStore, AlignmentType
from ..storage.classification_store import ClassificationStore
from ..storage.delta_store import DeltaStore
from ..storage.dna_store import DNAStore
from ..storage.definitions_store import DefinitionsStore
from ..storage.summary_store import SummaryStore

from .bands import SimilarityBand, get_similarity_band, get_band_distribution


# ---------------------------------------------------------------------------
# Policy Registry (lightweight metadata store)
# ---------------------------------------------------------------------------


def _ensure_registry_schema(conn: sqlite3.Connection) -> None:
    """Create policy registry table for metadata."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS policy_registry (
            doc_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            insurer TEXT,
            year INTEGER,
            category TEXT,
            scope TEXT,
            source_uri TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_registry_insurer
        ON policy_registry (insurer)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_registry_category
        ON policy_registry (category, scope)
        """
    )


class PolicyRegistry:
    """Registry for policy metadata."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or _default_db_path()

    def _connect(self) -> sqlite3.Connection:
        _ensure_parent(self.db_path)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        _ensure_registry_schema(conn)
        return conn

    def register(
        self,
        doc_id: str,
        name: str,
        *,
        insurer: str | None = None,
        year: int | None = None,
        category: str | None = None,
        scope: str | None = None,
        source_uri: str | None = None,
    ) -> None:
        """Register or update policy metadata."""
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO policy_registry (
                    doc_id, name, insurer, year, category, scope, source_uri,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(doc_id) DO UPDATE SET
                    name = excluded.name,
                    insurer = COALESCE(excluded.insurer, insurer),
                    year = COALESCE(excluded.year, year),
                    category = COALESCE(excluded.category, category),
                    scope = COALESCE(excluded.scope, scope),
                    source_uri = COALESCE(excluded.source_uri, source_uri),
                    updated_at = excluded.updated_at
                """,
                (doc_id, name, insurer, year, category, scope, source_uri, now, now),
            )

    def get(self, doc_id: str) -> dict | None:
        """Get policy metadata by doc_id."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM policy_registry WHERE doc_id = ?",
                (doc_id,),
            ).fetchone()
        if not row:
            return None
        return dict(row)

    def list_all(
        self,
        *,
        category: str | None = None,
        scope: str | None = None,
        insurer: str | None = None,
    ) -> List[dict]:
        """List all registered policies with optional filters."""
        query = "SELECT * FROM policy_registry WHERE 1=1"
        params: list = []

        if category:
            query += " AND category = ?"
            params.append(category)
        if scope:
            query += " AND scope = ?"
            params.append(scope)
        if insurer:
            query += " AND insurer = ?"
            params.append(insurer)

        query += " ORDER BY insurer ASC, year DESC, name ASC"

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Response DTOs
# ---------------------------------------------------------------------------


@dataclass
class PolicySummary:
    """Summary of a policy for listing."""
    doc_id: str
    name: str
    insurer: str | None = None
    year: int | None = None
    category: str | None = None
    scope: str | None = None
    block_count: int = 0
    section_count: int = 0


@dataclass
class SectionItem:
    """A section within a policy."""
    section_id: str
    title: str
    section_path: List[str]
    clause_count: int = 0
    similarity_score: float | None = None
    similarity_band: str | None = None
    similarity_color: str | None = None
    matched_count: int = 0
    unmatched_count: int = 0
    delta_count: int = 0


@dataclass
class ClauseItem:
    """A clause within a section."""
    block_id: str
    text: str
    clause_type: str
    section_path: List[str]
    page_number: int = 0
    is_matched: bool = False
    matched_block_id: str | None = None
    similarity_score: float | None = None
    similarity_band: str | None = None
    delta_count: int = 0
    confidence: float = 0.5


@dataclass
class ClausePairDetail:
    """Detail view for a matched clause pair."""
    block_id_a: str
    block_id_b: str
    text_a: str
    text_b: str
    clause_type: str
    section_path_a: List[str]
    section_path_b: List[str]
    alignment_score: float
    confidence: float
    deltas: List[Dict[str, Any]]
    evidence: Dict[str, Any]
    summary_bullets: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class SimilaritySummaryItem:
    """Similarity summary for a single policy comparison."""
    doc_id: str
    name: str
    insurer: str | None
    overall_score: float
    band: str
    color: str
    matched_count: int
    unmatched_count: int
    delta_count: int
    band_distribution: Dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Service Functions
# ---------------------------------------------------------------------------


def register_policy(
    doc_id: str,
    name: str,
    *,
    insurer: str | None = None,
    year: int | None = None,
    category: str | None = None,
    scope: str | None = None,
    source_uri: str | None = None,
) -> None:
    """Register policy metadata for listing/filtering."""
    registry = PolicyRegistry()
    registry.register(
        doc_id,
        name,
        insurer=insurer,
        year=year,
        category=category,
        scope=scope,
        source_uri=source_uri,
    )


def list_policies(
    *,
    category: str | None = None,
    scope: str | None = None,
    insurer: str | None = None,
) -> List[PolicySummary]:
    """List all available policies with optional filters.
    
    Returns policies that have been processed and registered.
    """
    registry = PolicyRegistry()
    layout_store = LayoutStore()
    classification_store = ClassificationStore()

    policies = registry.list_all(category=category, scope=scope, insurer=insurer)
    results: List[PolicySummary] = []

    for policy in policies:
        doc_id = policy["doc_id"]
        
        # Get block count
        blocks = layout_store.get_blocks(doc_id)
        block_count = len(blocks)
        
        # Count unique sections
        sections = set()
        for block in blocks:
            if block.section_path:
                sections.add(tuple(block.section_path))
        
        results.append(
            PolicySummary(
                doc_id=doc_id,
                name=policy["name"],
                insurer=policy.get("insurer"),
                year=policy.get("year"),
                category=policy.get("category"),
                scope=policy.get("scope"),
                block_count=block_count,
                section_count=len(sections),
            )
        )

    return results


def get_policy_sections(
    doc_id: str,
    *,
    compare_to_doc_id: str | None = None,
) -> List[SectionItem]:
    """Get section tree for a policy with optional similarity indicators.
    
    Args:
        doc_id: The policy document ID
        compare_to_doc_id: Optional other policy to show similarity against
        
    Returns:
        List of sections with similarity indicators if comparing.
    """
    layout_store = LayoutStore()
    classification_store = ClassificationStore()
    alignment_store = AlignmentStore()
    delta_store = DeltaStore()

    blocks = layout_store.get_blocks(doc_id)
    classifications = classification_store.get_all_classifications(doc_id)
    
    # Build classification lookup
    class_lookup = {c.block_id: c for c in classifications}
    
    # Group blocks by section
    section_blocks: Dict[tuple, List] = defaultdict(list)
    for block in blocks:
        section_key = tuple(block.section_path) if block.section_path else ("Uncategorized",)
        section_blocks[section_key].append(block)
    
    # Get alignments and deltas if comparing
    alignments = []
    deltas = []
    if compare_to_doc_id:
        alignments = alignment_store.get_alignments(doc_id, compare_to_doc_id)
        deltas = delta_store.get_deltas(doc_id, compare_to_doc_id)
    
    # Build alignment lookups
    alignment_by_block = {}
    for a in alignments:
        alignment_by_block[a.block_id_a] = a
    
    # Build delta count lookup
    delta_counts: Dict[str, int] = defaultdict(int)
    for d in deltas:
        delta_counts[d.block_id_a] += 1
    
    # Build section items
    results: List[SectionItem] = []
    for section_path, section_block_list in sorted(section_blocks.items()):
        # Use double underscore as segment delimiter, single underscore for spaces within segments
        section_id = "__".join(seg.replace(" ", "_").lower() for seg in section_path)
        title = section_path[-1] if section_path else "Uncategorized"
        
        # Calculate section-level similarity if comparing
        section_scores = []
        matched_count = 0
        unmatched_count = 0
        section_delta_count = 0
        
        for block in section_block_list:
            if block.id in alignment_by_block:
                alignment = alignment_by_block[block.id]
                if alignment.alignment_type != AlignmentType.UNMATCHED:
                    section_scores.append(alignment.alignment_score)
                    matched_count += 1
                else:
                    unmatched_count += 1
            else:
                unmatched_count += 1
            
            section_delta_count += delta_counts.get(block.id, 0)
        
        # Calculate average similarity for section
        similarity_score = None
        similarity_band = None
        similarity_color = None
        
        if section_scores:
            similarity_score = sum(section_scores) / len(section_scores)
            band_config = get_similarity_band(similarity_score)
            similarity_band = band_config.band.value
            similarity_color = band_config.color
        
        results.append(
            SectionItem(
                section_id=section_id,
                title=title,
                section_path=list(section_path),
                clause_count=len(section_block_list),
                similarity_score=similarity_score,
                similarity_band=similarity_band,
                similarity_color=similarity_color,
                matched_count=matched_count,
                unmatched_count=unmatched_count,
                delta_count=section_delta_count,
            )
        )
    
    return results


def get_section_detail(
    doc_id: str,
    section_path: List[str],
    *,
    compare_to_doc_id: str | None = None,
) -> List[ClauseItem]:
    """Get clauses within a section with match/delta info.
    
    Args:
        doc_id: The policy document ID
        section_path: Path to the section (e.g., ["Cover", "Fire"])
        compare_to_doc_id: Optional other policy for comparison
        
    Returns:
        List of clauses with alignment and delta indicators.
    """
    layout_store = LayoutStore()
    classification_store = ClassificationStore()
    alignment_store = AlignmentStore()
    delta_store = DeltaStore()

    blocks = layout_store.get_blocks(doc_id)
    classifications = classification_store.get_all_classifications(doc_id)
    
    class_lookup = {c.block_id: c for c in classifications}
    
    # Filter to section
    section_key = tuple(section_path)
    section_blocks = [
        b for b in blocks
        if tuple(b.section_path) == section_key
    ]
    
    # Get alignments and deltas if comparing
    alignment_by_block = {}
    delta_counts: Dict[str, int] = defaultdict(int)
    
    if compare_to_doc_id:
        alignments = alignment_store.get_alignments(doc_id, compare_to_doc_id)
        deltas = delta_store.get_deltas(doc_id, compare_to_doc_id)
        
        for a in alignments:
            alignment_by_block[a.block_id_a] = a
        for d in deltas:
            delta_counts[d.block_id_a] += 1
    
    results: List[ClauseItem] = []
    for block in section_blocks:
        classification = class_lookup.get(block.id)
        clause_type = classification.clause_type.value if classification else "UNKNOWN"
        
        # Alignment info
        is_matched = False
        matched_block_id = None
        similarity_score = None
        similarity_band = None
        confidence = 0.5
        
        if block.id in alignment_by_block:
            alignment = alignment_by_block[block.id]
            if alignment.alignment_type != AlignmentType.UNMATCHED:
                is_matched = True
                matched_block_id = alignment.block_id_b
                similarity_score = alignment.alignment_score
                band_config = get_similarity_band(similarity_score)
                similarity_band = band_config.band.value
                confidence = alignment.confidence
        
        results.append(
            ClauseItem(
                block_id=block.id,
                text=block.text,
                clause_type=clause_type,
                section_path=list(block.section_path),
                page_number=block.page_number,
                is_matched=is_matched,
                matched_block_id=matched_block_id,
                similarity_score=similarity_score,
                similarity_band=similarity_band,
                delta_count=delta_counts.get(block.id, 0),
                confidence=confidence,
            )
        )
    
    return results


def get_clause_pair(
    doc_id_a: str,
    block_id_a: str,
    doc_id_b: str,
) -> ClausePairDetail | None:
    """Get detailed view of a matched clause pair.
    
    Args:
        doc_id_a: First policy document ID
        block_id_a: Block ID from first policy
        doc_id_b: Second policy document ID
        
    Returns:
        Detailed clause pair with texts, deltas, and evidence.
    """
    layout_store = LayoutStore()
    alignment_store = AlignmentStore()
    delta_store = DeltaStore()
    summary_store = SummaryStore()
    classification_store = ClassificationStore()

    # Get alignment
    alignments = alignment_store.get_alignment(block_id_a)
    alignment = None
    for a in alignments:
        if a.doc_id_b == doc_id_b:
            alignment = a
            break
    
    if not alignment or alignment.alignment_type == AlignmentType.UNMATCHED:
        return None
    
    # Get blocks
    blocks_a = layout_store.get_blocks(doc_id_a)
    blocks_b = layout_store.get_blocks(doc_id_b)
    
    block_a = next((b for b in blocks_a if b.id == block_id_a), None)
    block_b = next((b for b in blocks_b if b.id == alignment.block_id_b), None)
    
    if not block_a or not block_b:
        return None
    
    # Get deltas for this pair
    all_deltas = delta_store.get_deltas(doc_id_a, doc_id_b)
    pair_deltas = [
        d for d in all_deltas
        if d.block_id_a == block_id_a and d.block_id_b == alignment.block_id_b
    ]
    
    # Format deltas
    deltas_formatted = []
    evidence_combined: Dict[str, Any] = {}
    
    for delta in pair_deltas:
        deltas_formatted.append({
            "delta_type": delta.delta_type.value,
            "direction": delta.direction.value,
            "details": delta.details,
            "confidence": delta.confidence,
        })
        evidence_combined.update(delta.evidence)
    
    # Get relevant summary bullets
    summary = summary_store.get_summary(doc_id_a, doc_id_b)
    relevant_bullets = []
    if summary:
        for bullet in summary.bullets:
            if bullet.evidence_refs.block_id_a == block_id_a:
                relevant_bullets.append(bullet.to_dict())
    
    return ClausePairDetail(
        block_id_a=block_id_a,
        block_id_b=alignment.block_id_b,
        text_a=block_a.text,
        text_b=block_b.text,
        clause_type=alignment.clause_type,
        section_path_a=list(block_a.section_path),
        section_path_b=list(block_b.section_path),
        alignment_score=alignment.alignment_score,
        confidence=alignment.confidence,
        deltas=deltas_formatted,
        evidence=evidence_combined,
        summary_bullets=relevant_bullets,
    )


def get_similarity_summary(
    doc_id: str,
    *,
    category: str | None = None,
    scope: str | None = None,
) -> List[SimilaritySummaryItem]:
    """Get similarity ranking of other policies compared to this one.
    
    Args:
        doc_id: The active/reference policy document ID
        category: Optional filter for category
        scope: Optional filter for scope
        
    Returns:
        List of policies ranked by similarity to the reference.
    """
    registry = PolicyRegistry()
    alignment_store = AlignmentStore()
    delta_store = DeltaStore()

    # Get all policies (filtered)
    all_policies = registry.list_all(category=category, scope=scope)
    
    results: List[SimilaritySummaryItem] = []
    
    for policy in all_policies:
        other_doc_id = policy["doc_id"]
        
        # Skip self
        if other_doc_id == doc_id:
            continue
        
        # Get alignments (try both directions)
        alignments = alignment_store.get_alignments(doc_id, other_doc_id)
        if not alignments:
            alignments = alignment_store.get_alignments(other_doc_id, doc_id)
        
        if not alignments:
            # No comparison data available
            continue
        
        # Calculate summary stats
        scores = []
        matched_count = 0
        unmatched_count = 0
        
        for a in alignments:
            if a.alignment_type == AlignmentType.UNMATCHED:
                unmatched_count += 1
            else:
                matched_count += 1
                scores.append(a.alignment_score)
        
        # Get delta count
        deltas = delta_store.get_deltas(doc_id, other_doc_id)
        if not deltas:
            deltas = delta_store.get_deltas(other_doc_id, doc_id)
        delta_count = len(deltas)
        
        # Calculate overall score
        if scores:
            overall_score = sum(scores) / len(scores)
        else:
            overall_score = 0.0
        
        band_config = get_similarity_band(overall_score)
        band_distribution = get_band_distribution(scores)
        
        results.append(
            SimilaritySummaryItem(
                doc_id=other_doc_id,
                name=policy["name"],
                insurer=policy.get("insurer"),
                overall_score=overall_score,
                band=band_config.band.value,
                color=band_config.color,
                matched_count=matched_count,
                unmatched_count=unmatched_count,
                delta_count=delta_count,
                band_distribution=band_distribution,
            )
        )
    
    # Sort by overall score descending
    results.sort(key=lambda x: x.overall_score, reverse=True)
    
    return results


# =============================================================================
# DeliveryService: Constructs full comparison results from persisted data
# =============================================================================


class DeliveryService:
    """Service for constructing full comparison results from segments 1-7 outputs.
    
    Used by the async job system to assemble UCCComparisonResult from persisted
    alignment, delta, and summary data.
    """

    def __init__(self):
        self.layout_store = LayoutStore()
        self.alignment_store = AlignmentStore()
        self.delta_store = DeltaStore()
        self.summary_store = SummaryStore()
        self.classification_store = ClassificationStore()

    def get_comparison_result(
        self,
        doc_id_a: str,
        doc_id_b: str,
    ) -> Dict[str, Any]:
        """Construct full UCCComparisonResult from persisted comparison data.
        
        Assembles the result from the outputs of all 7 segments:
        - Segments 1-4: Document preprocessing (blocks, classifications, DNA)
        - Segments 5-7: Comparison outputs (alignments, deltas, summary)
        
        Args:
            doc_id_a: First document ID
            doc_id_b: Second document ID
            
        Returns:
            UCCComparisonResult-compatible dict with all comparison data
        """
        # Get alignments
        alignments = self.alignment_store.get_alignments(doc_id_a, doc_id_b)
        
        # Get deltas
        deltas = self.delta_store.get_deltas(doc_id_a, doc_id_b)
        
        # Get summary
        summary_result = self.summary_store.get_summary(doc_id_a, doc_id_b)
        
        # Get blocks for text lookup
        blocks_a = self.layout_store.get_blocks(doc_id_a)
        blocks_b = self.layout_store.get_blocks(doc_id_b)
        
        text_map_a = {b.id: b.text for b in blocks_a}
        text_map_b = {b.id: b.text for b in blocks_b}
        
        # Get classifications
        classifications_a = self.classification_store.get_all_classifications(doc_id_a)
        classifications_b = self.classification_store.get_all_classifications(doc_id_b)
        
        class_map_a = {c.block_id: c.clause_type.value for c in classifications_a}
        class_map_b = {c.block_id: c.clause_type.value for c in classifications_b}
        
        # Build matches list (aligned + unmatched)
        matches = []
        
        # Add matched pairs
        for alignment in alignments:
            if alignment.alignment_type != AlignmentType.UNMATCHED and alignment.block_id_b:
                # Find related deltas
                alignment_deltas = [d for d in deltas 
                                  if d.block_id_a == alignment.block_id_a 
                                  and d.block_id_b == alignment.block_id_b]
                
                # Determine match status based on deltas
                status = "unchanged"
                if alignment_deltas:
                    # Has deltas = modified
                    status = "modified"
                
                matches.append({
                    "a_id": alignment.block_id_a,
                    "b_id": alignment.block_id_b,
                    "similarity": alignment.alignment_score,
                    "status": status,
                    "materiality_score": alignment.confidence,
                    "a_text": text_map_a.get(alignment.block_id_a, ""),
                    "b_text": text_map_b.get(alignment.block_id_b, ""),
                    "a_title": class_map_a.get(alignment.block_id_a, "UNKNOWN"),
                    "b_title": class_map_b.get(alignment.block_id_b, "UNKNOWN"),
                })
        
        # Add unmatched blocks from A
        unmapped_a = []
        for alignment in alignments:
            if alignment.alignment_type == AlignmentType.UNMATCHED:
                unmapped_a.append(alignment.block_id_a)
                matches.append({
                    "a_id": alignment.block_id_a,
                    "b_id": None,
                    "similarity": 0.0,
                    "status": "removed",
                    "materiality_score": alignment.confidence,
                    "a_text": text_map_a.get(alignment.block_id_a, ""),
                    "b_text": None,
                    "a_title": class_map_a.get(alignment.block_id_a, "UNKNOWN"),
                    "b_title": None,
                })
        
        # Identify unmapped B (blocks with no alignment to A)
        unmapped_b = []
        matched_b_ids = {a.block_id_b for a in alignments 
                        if a.block_id_b and a.alignment_type != AlignmentType.UNMATCHED}
        
        for block_b in blocks_b:
            if block_b.id not in matched_b_ids:
                unmapped_b.append(block_b.id)
                matches.append({
                    "a_id": None,
                    "b_id": block_b.id,
                    "similarity": 0.0,
                    "status": "added",
                    "materiality_score": 0.5,
                    "a_text": None,
                    "b_text": text_map_b.get(block_b.id, ""),
                    "a_title": None,
                    "b_title": class_map_b.get(block_b.id, "UNKNOWN"),
                })
        
        # Count statuses for the summary
        status_counts = {"added": 0, "removed": 0, "modified": 0, "unchanged": 0}
        for m in matches:
            s = m.get("status", "unchanged")
            if s in status_counts:
                status_counts[s] += 1
        
        # Build summary bullets from the narrative summary
        bullets: list[str] = []
        if summary_result and summary_result.bullets:
            bullets = [b.text if hasattr(b, "text") else str(b) for b in summary_result.bullets]
        
        # Build summary dict matching frontend Summary type
        summary = {
            "counts": status_counts,
            "bullets": bullets,
        }
        
        # Ensure every match has all required fields for the frontend ClauseMatch type
        for m in matches:
            m.setdefault("token_diff", None)
            m.setdefault("numeric_delta", None)
            m.setdefault("strictness_delta", 0)
            m.setdefault("review_required", False)
            m.setdefault("evidence", {})
            m.setdefault("clause_type", m.get("a_title") or m.get("b_title") or "UNCERTAIN")
        
        # Build final result matching UCCComparisonResult structure
        return {
            "summary": summary,
            "matches": matches,
            "unmapped_a": unmapped_a,
            "unmapped_b": unmapped_b,
            "warnings": [],
            "timings_ms": {
                "parse_a": 0.0,
                "parse_b": 0.0,
                "align": 0.0,
                "diff": 0.0,
                "total": 0.0,
            },
        }
