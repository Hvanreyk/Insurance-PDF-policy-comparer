"""Segment 7: Narrative Summarisation Agent (Evidence-Bound Bullets).

Generates human-readable bullets from Segment 6 deltas that are:
- concise
- factual (no legal advice)
- evidence-bound (every bullet references specific block IDs + evidence)
- safe for broker/client review
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Tuple

from ..storage.alignment_store import AlignmentStore, AlignmentType
from ..storage.delta_store import ClauseDelta, DeltaDirection, DeltaStore, DeltaType
from ..storage.layout_store import LayoutStore
from ..storage.summary_store import (
    BulletDirection,
    BulletSeverity,
    EvidenceRef,
    NarrativeResult,
    SummaryBullet,
    SummaryCounts,
    SummaryStore,
)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Maximum bullets to include in summary
MAX_BULLETS = 12
MIN_BULLETS = 5

# Confidence threshold below which bullets get REVIEW severity
REVIEW_CONFIDENCE_THRESHOLD = 0.5

# Clause types with higher severity (impact on coverage)
HIGH_SEVERITY_CLAUSE_TYPES = {"EXCLUSION", "CONDITION", "LIMIT", "SUBLIMIT", "WARRANTY"}

# Delta types with higher severity
HIGH_SEVERITY_DELTA_TYPES = {
    DeltaType.STRICTNESS_CHANGE,
    DeltaType.NUMERIC_CHANGE,
    DeltaType.SCOPE_CHANGE,
    DeltaType.CARVE_OUT_CHANGE,
}

# Maximum length of quote fragments
MAX_QUOTE_LENGTH = 80


# ---------------------------------------------------------------------------
# Bullet Templates (Deterministic)
# ---------------------------------------------------------------------------


def _truncate(text: str, max_length: int = MAX_QUOTE_LENGTH) -> str:
    """Truncate text with ellipsis if too long."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3].rsplit(" ", 1)[0] + "..."


def _format_list(items: List[str], max_items: int = 3) -> str:
    """Format a list for display."""
    if not items:
        return ""
    if len(items) <= max_items:
        return ", ".join(f'"{item}"' for item in items)
    shown = items[:max_items]
    return ", ".join(f'"{item}"' for item in shown) + f" (+{len(items) - max_items} more)"


def _generate_scope_bullet(delta: ClauseDelta) -> str:
    """Generate bullet text for scope change."""
    details = delta.details
    direction = delta.direction
    
    parts = []
    
    if direction == DeltaDirection.BROADER:
        if details.get("added_connectors"):
            connectors = _format_list(details["added_connectors"])
            parts.append(f"added scope connectors: {connectors}")
        if details.get("added_entities"):
            entities = _format_list(details["added_entities"])
            parts.append(f"added entities: {entities}")
        action = "Scope appears broader"
    elif direction == DeltaDirection.NARROWER:
        if details.get("removed_connectors"):
            connectors = _format_list(details["removed_connectors"])
            parts.append(f"removed scope connectors: {connectors}")
        if details.get("removed_entities"):
            entities = _format_list(details["removed_entities"])
            parts.append(f"removed entities: {entities}")
        action = "Scope appears narrower"
    else:
        action = "Scope changed"
        if details.get("added_connectors"):
            parts.append(f"added: {_format_list(details['added_connectors'])}")
        if details.get("removed_connectors"):
            parts.append(f"removed: {_format_list(details['removed_connectors'])}")
    
    if parts:
        return f"{action} — {'; '.join(parts)}."
    return f"{action}."


def _generate_strictness_bullet(delta: ClauseDelta) -> str:
    """Generate bullet text for strictness change."""
    details = delta.details
    direction = delta.direction
    
    from_strict = details.get("from_strictness", "unknown")
    to_strict = details.get("to_strictness", "unknown")
    
    if direction == DeltaDirection.BROADER:
        return f"Strictness reduced from {from_strict} to {to_strict} — clause may apply less rigidly."
    elif direction == DeltaDirection.NARROWER:
        return f"Strictness increased from {from_strict} to {to_strict} — clause may apply more rigidly."
    else:
        return f"Strictness changed from {from_strict} to {to_strict} — review for impact."


def _generate_carve_out_bullet(delta: ClauseDelta) -> str:
    """Generate bullet text for carve-out change."""
    details = delta.details
    direction = delta.direction
    
    if direction == DeltaDirection.BROADER:
        if details.get("added_carve_outs"):
            carve_outs = _format_list(details["added_carve_outs"], max_items=2)
            return f"Carve-out/exception added: {carve_outs}."
        elif details.get("removed_carve_outs"):
            carve_outs = _format_list(details["removed_carve_outs"], max_items=2)
            return f"Carve-out/exception removed: {carve_outs}."
    elif direction == DeltaDirection.NARROWER:
        if details.get("added_carve_outs"):
            carve_outs = _format_list(details["added_carve_outs"], max_items=2)
            return f"Carve-out/exception added: {carve_outs}."
        elif details.get("removed_carve_outs"):
            carve_outs = _format_list(details["removed_carve_outs"], max_items=2)
            return f"Carve-out/exception removed: {carve_outs}."
    
    # Ambiguous case
    parts = []
    if details.get("added_carve_outs"):
        parts.append(f"added: {_format_list(details['added_carve_outs'], max_items=2)}")
    if details.get("removed_carve_outs"):
        parts.append(f"removed: {_format_list(details['removed_carve_outs'], max_items=2)}")
    
    if parts:
        return f"Carve-out changes: {'; '.join(parts)}. Review for impact."
    return "Carve-out changes detected — review for impact."


def _generate_burden_shift_bullet(delta: ClauseDelta) -> str:
    """Generate bullet text for burden shift change."""
    details = delta.details
    direction = delta.direction
    
    from_burden = details.get("from_burden_shift", False)
    to_burden = details.get("to_burden_shift", False)
    
    if direction == DeltaDirection.NARROWER:
        return "Insured obligations added — additional duties or notification requirements introduced."
    elif direction == DeltaDirection.BROADER:
        return "Insured obligations reduced — fewer duties or notification requirements."
    else:
        return f"Burden shift changed from {from_burden} to {to_burden} — review impact on insured obligations."


def _generate_numeric_bullet(delta: ClauseDelta) -> str:
    """Generate bullet text for numeric change."""
    details = delta.details
    direction = delta.direction
    
    parts = []
    
    # Only use numbers from delta.details (no hallucination)
    for key, change in details.items():
        if isinstance(change, dict) and "from" in change and "to" in change:
            from_val = change["from"]
            to_val = change["to"]
            
            # Format numbers nicely
            if isinstance(from_val, (int, float)) and isinstance(to_val, (int, float)):
                if from_val >= 1000:
                    from_str = f"${from_val:,.0f}"
                else:
                    from_str = str(from_val)
                if to_val >= 1000:
                    to_str = f"${to_val:,.0f}"
                else:
                    to_str = str(to_val)
            else:
                from_str = str(from_val)
                to_str = str(to_val)
            
            # Clean up key name for display
            display_key = key.replace("_", " ").replace("increased", "").replace("decreased", "").strip()
            parts.append(f"{display_key}: {from_str} → {to_str}")
    
    if not parts:
        return "Numeric values changed — review for specific amounts."
    
    changes = "; ".join(parts)
    
    if direction == DeltaDirection.BROADER:
        return f"Numeric change (appears more favourable): {changes}."
    elif direction == DeltaDirection.NARROWER:
        return f"Numeric change (appears less favourable): {changes}."
    else:
        return f"Numeric change: {changes}."


def _generate_definition_dependency_bullet(delta: ClauseDelta) -> str:
    """Generate bullet text for definition dependency change."""
    details = delta.details
    
    parts = []
    if details.get("added_dependencies"):
        deps = _format_list(details["added_dependencies"])
        parts.append(f"new defined terms referenced: {deps}")
    if details.get("removed_dependencies"):
        deps = _format_list(details["removed_dependencies"])
        parts.append(f"defined terms no longer referenced: {deps}")
    
    if parts:
        return f"Definition dependencies changed — {'; '.join(parts)}. Review definitions for impact."
    return "Definition dependencies changed — review referenced definitions for impact."


def _generate_temporal_bullet(delta: ClauseDelta) -> str:
    """Generate bullet text for temporal change."""
    details = delta.details
    direction = delta.direction
    
    if direction == DeltaDirection.BROADER:
        if details.get("removed_constraints"):
            constraints = _format_list(details["removed_constraints"])
            return f"Timing constraint removed: {constraints}."
    elif direction == DeltaDirection.NARROWER:
        if details.get("added_constraints"):
            constraints = _format_list(details["added_constraints"])
            return f"Timing constraint added: {constraints}."
    
    parts = []
    if details.get("added_constraints"):
        parts.append(f"added: {_format_list(details['added_constraints'])}")
    if details.get("removed_constraints"):
        parts.append(f"removed: {_format_list(details['removed_constraints'])}")
    
    if parts:
        return f"Timing constraints changed: {'; '.join(parts)}."
    return "Timing constraints changed — review for notification/period requirements."


# Template dispatcher
BULLET_TEMPLATES = {
    DeltaType.SCOPE_CHANGE: _generate_scope_bullet,
    DeltaType.STRICTNESS_CHANGE: _generate_strictness_bullet,
    DeltaType.CARVE_OUT_CHANGE: _generate_carve_out_bullet,
    DeltaType.BURDEN_SHIFT_CHANGE: _generate_burden_shift_bullet,
    DeltaType.NUMERIC_CHANGE: _generate_numeric_bullet,
    DeltaType.DEFINITION_DEPENDENCY_CHANGE: _generate_definition_dependency_bullet,
    DeltaType.TEMPORAL_CHANGE: _generate_temporal_bullet,
}


# ---------------------------------------------------------------------------
# Severity Scoring
# ---------------------------------------------------------------------------


def _compute_severity(
    delta: ClauseDelta,
    alignment_confidence: float,
) -> Tuple[BulletSeverity, float]:
    """
    Compute severity and confidence for a bullet.
    
    Returns (severity, confidence).
    """
    # Start with delta confidence
    confidence = delta.confidence
    
    # Factor in alignment confidence
    confidence = min(confidence, alignment_confidence)
    
    # Low confidence → REVIEW
    if confidence < REVIEW_CONFIDENCE_THRESHOLD:
        return BulletSeverity.REVIEW, confidence
    
    # High severity clause types
    clause_type_high = delta.clause_type in HIGH_SEVERITY_CLAUSE_TYPES
    
    # High severity delta types
    delta_type_high = delta.delta_type in HIGH_SEVERITY_DELTA_TYPES
    
    # Direction affects severity (narrower = higher concern)
    direction_high = delta.direction == DeltaDirection.NARROWER
    
    # Score
    score = 0
    if clause_type_high:
        score += 2
    if delta_type_high:
        score += 2
    if direction_high:
        score += 1
    if delta.direction == DeltaDirection.AMBIGUOUS:
        score += 1  # Ambiguous needs attention
    
    if score >= 4:
        return BulletSeverity.HIGH, confidence
    elif score >= 2:
        return BulletSeverity.MEDIUM, confidence
    else:
        return BulletSeverity.LOW, confidence


# ---------------------------------------------------------------------------
# Evidence Extraction
# ---------------------------------------------------------------------------


def _extract_evidence(
    delta: ClauseDelta,
    text_a: str,
    text_b: str | None,
) -> EvidenceRef:
    """Extract evidence references from a delta."""
    # Generate delta ID
    delta_id = hashlib.sha256(
        f"{delta.doc_id_a}:{delta.block_id_a}:{delta.doc_id_b}:{delta.block_id_b}:{delta.delta_type.value}".encode()
    ).hexdigest()[:12]
    
    # Extract quote fragments from evidence
    fragments: List[str] = []
    evidence = delta.evidence
    
    # Get relevant fragments based on delta type
    if delta.delta_type == DeltaType.SCOPE_CHANGE:
        for key in ["connectors_a", "connectors_b", "entities_a", "entities_b"]:
            if key in evidence and evidence[key]:
                fragments.extend(evidence[key][:2])
    elif delta.delta_type == DeltaType.CARVE_OUT_CHANGE:
        for key in ["carve_outs_a", "carve_outs_b"]:
            if key in evidence and evidence[key]:
                fragments.extend([_truncate(c, 60) for c in evidence[key][:2]])
    elif delta.delta_type == DeltaType.NUMERIC_CHANGE:
        # Don't add quote fragments for numeric - just reference the numbers
        pass
    elif delta.delta_type == DeltaType.TEMPORAL_CHANGE:
        for key in ["constraints_a", "constraints_b"]:
            if key in evidence and evidence[key]:
                fragments.extend(evidence[key][:2])
    
    # Add text snippets if no other fragments
    if not fragments:
        if text_a:
            fragments.append(_truncate(text_a, 50))
        if text_b:
            fragments.append(_truncate(text_b, 50))
    
    return EvidenceRef(
        block_id_a=delta.block_id_a,
        block_id_b=delta.block_id_b,
        delta_ids=[delta_id],
        quote_fragments=fragments[:4],  # Limit to 4 fragments
    )


# ---------------------------------------------------------------------------
# Bullet Generation
# ---------------------------------------------------------------------------


def _generate_bullet_id(delta: ClauseDelta, index: int) -> str:
    """Generate a stable bullet ID."""
    return hashlib.sha256(
        f"{delta.doc_id_a}:{delta.block_id_a}:{delta.delta_type.value}:{index}".encode()
    ).hexdigest()[:10]


def _delta_direction_to_bullet(direction: DeltaDirection) -> BulletDirection:
    """Convert delta direction to bullet direction."""
    mapping = {
        DeltaDirection.BROADER: BulletDirection.BROADER,
        DeltaDirection.NARROWER: BulletDirection.NARROWER,
        DeltaDirection.NEUTRAL: BulletDirection.NEUTRAL,
        DeltaDirection.AMBIGUOUS: BulletDirection.AMBIGUOUS,
    }
    return mapping.get(direction, BulletDirection.AMBIGUOUS)


def _generate_bullet_from_delta(
    delta: ClauseDelta,
    alignment_confidence: float,
    text_a: str,
    text_b: str | None,
    index: int,
) -> SummaryBullet:
    """Generate a summary bullet from a delta."""
    # Generate bullet text using template
    template_fn = BULLET_TEMPLATES.get(delta.delta_type)
    if template_fn:
        text = template_fn(delta)
    else:
        text = f"{delta.delta_type.value.replace('_', ' ').title()} detected — review for impact."
    
    # Add block reference to text
    block_ref = f"[A:{delta.block_id_a}"
    if delta.block_id_b:
        block_ref += f" ↔ B:{delta.block_id_b}"
    block_ref += "]"
    text = f"{text} {block_ref}"
    
    # Compute severity
    severity, confidence = _compute_severity(delta, alignment_confidence)
    
    # Extract evidence
    evidence = _extract_evidence(delta, text_a, text_b)
    
    return SummaryBullet(
        bullet_id=_generate_bullet_id(delta, index),
        text=text,
        severity=severity,
        delta_types=[delta.delta_type.value],
        direction=_delta_direction_to_bullet(delta.direction),
        evidence_refs=evidence,
        clause_type=delta.clause_type,
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# Main Summarisation Function
# ---------------------------------------------------------------------------


def run_narrative_summarisation(
    doc_id_a: str,
    doc_id_b: str,
) -> NarrativeResult:
    """
    Run the Narrative Summarisation Agent.
    
    Generates human-readable, evidence-bound bullets from detected deltas.
    
    Args:
        doc_id_a: First document ID
        doc_id_b: Second document ID
    
    Returns:
        NarrativeResult containing summary bullets and counts.
    """
    # Load alignments from Segment 5
    alignment_store = AlignmentStore()
    alignments = alignment_store.get_alignments(doc_id_a, doc_id_b)
    
    # Load deltas from Segment 6
    delta_store = DeltaStore()
    deltas = delta_store.get_deltas(doc_id_a, doc_id_b)
    
    # Load block texts for evidence
    layout_store = LayoutStore()
    blocks_a = layout_store.get_blocks(doc_id_a)
    blocks_b = layout_store.get_blocks(doc_id_b)
    
    text_map_a = {b.id: b.text for b in blocks_a}
    text_map_b = {b.id: b.text for b in blocks_b}
    
    # Build alignment confidence map
    alignment_confidence_map: Dict[str, float] = {}
    for alignment in alignments:
        alignment_confidence_map[alignment.block_id_a] = alignment.confidence
    
    # Count matched/unmatched
    matched_count = sum(
        1 for a in alignments if a.alignment_type != AlignmentType.UNMATCHED
    )
    unmatched_count = sum(
        1 for a in alignments if a.alignment_type == AlignmentType.UNMATCHED
    )
    
    # Count deltas by type
    deltas_by_type: Dict[str, int] = {}
    for delta in deltas:
        key = delta.delta_type.value
        deltas_by_type[key] = deltas_by_type.get(key, 0) + 1
    
    # Generate bullets from deltas
    bullets: List[SummaryBullet] = []
    
    for i, delta in enumerate(deltas):
        alignment_conf = alignment_confidence_map.get(delta.block_id_a, 0.5)
        text_a = text_map_a.get(delta.block_id_a, "")
        text_b = text_map_b.get(delta.block_id_b, "") if delta.block_id_b else None
        
        bullet = _generate_bullet_from_delta(
            delta=delta,
            alignment_confidence=alignment_conf,
            text_a=text_a,
            text_b=text_b,
            index=i,
        )
        bullets.append(bullet)
    
    # Sort by severity (HIGH first) then confidence (highest first)
    severity_order = {
        BulletSeverity.HIGH: 0,
        BulletSeverity.MEDIUM: 1,
        BulletSeverity.LOW: 2,
        BulletSeverity.REVIEW: 3,
    }
    bullets.sort(key=lambda b: (severity_order[b.severity], -b.confidence))
    
    # Limit to top N bullets
    if len(bullets) > MAX_BULLETS:
        bullets = bullets[:MAX_BULLETS]
    
    # Count review-needed
    review_count = sum(1 for b in bullets if b.severity == BulletSeverity.REVIEW)
    
    # Calculate overall confidence
    if bullets:
        overall_confidence = sum(b.confidence for b in bullets) / len(bullets)
    else:
        overall_confidence = 0.5
    
    # Build counts
    counts = SummaryCounts(
        matched_clauses=matched_count,
        unmatched_clauses=unmatched_count,
        deltas_by_type=deltas_by_type,
        review_needed=review_count,
        total_bullets=len(bullets),
    )
    
    # Build result
    result = NarrativeResult(
        doc_id_a=doc_id_a,
        doc_id_b=doc_id_b,
        bullets=bullets,
        counts=counts,
        confidence=round(overall_confidence, 4),
        model_info=None,  # No LLM used (deterministic templates)
    )
    
    # Persist
    summary_store = SummaryStore()
    summary_store.clear_summary(doc_id_a, doc_id_b)
    summary_store.persist_summary(result)
    
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_summary(doc_id_a: str, doc_id_b: str) -> NarrativeResult | None:
    """Retrieve the narrative summary for a document pair."""
    store = SummaryStore()
    return store.get_summary(doc_id_a, doc_id_b)


def get_bullets(
    doc_id_a: str,
    doc_id_b: str,
    severity: BulletSeverity | None = None,
) -> List[SummaryBullet]:
    """Retrieve bullets for a document pair, optionally filtered by severity."""
    store = SummaryStore()
    return store.get_bullets(doc_id_a, doc_id_b, severity)
