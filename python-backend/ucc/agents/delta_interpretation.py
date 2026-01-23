"""Segment 6: Delta Interpretation Agent (Structured Change Detection).

Converts aligned clause pairs into structured, factual change signals
describing how legal effect differs, without interpretation or advice.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Set, Tuple

from ..storage.alignment_store import AlignmentStore, AlignmentType, ClauseAlignment
from ..storage.delta_store import (
    ClauseDelta,
    DeltaDirection,
    DeltaResult,
    DeltaStore,
    DeltaType,
)
from ..storage.dna_store import ClauseDNA, DNAStore, Polarity, Strictness


# ---------------------------------------------------------------------------
# Delta Detection Functions
# ---------------------------------------------------------------------------


def detect_scope_change(
    dna_a: ClauseDNA,
    dna_b: ClauseDNA,
) -> Tuple[DeltaDirection | None, Dict[str, Any], Dict[str, Any]]:
    """
    Detect scope changes by comparing scope_connectors and entities.
    
    Rules:
    - More connectors/broader entities in B → broader
    - Fewer connectors in B → narrower
    """
    connectors_a = set(dna_a.scope_connectors)
    connectors_b = set(dna_b.scope_connectors)
    
    entities_a = set(dna_a.entities)
    entities_b = set(dna_b.entities)
    
    # No change
    if connectors_a == connectors_b and entities_a == entities_b:
        return None, {}, {}
    
    # Build details
    details: Dict[str, Any] = {}
    evidence: Dict[str, Any] = {}
    
    added_connectors = connectors_b - connectors_a
    removed_connectors = connectors_a - connectors_b
    added_entities = entities_b - entities_a
    removed_entities = entities_a - entities_b
    
    if added_connectors:
        details["added_connectors"] = list(added_connectors)
    if removed_connectors:
        details["removed_connectors"] = list(removed_connectors)
    if added_entities:
        details["added_entities"] = list(added_entities)
    if removed_entities:
        details["removed_entities"] = list(removed_entities)
    
    evidence["connectors_a"] = list(connectors_a)
    evidence["connectors_b"] = list(connectors_b)
    evidence["entities_a"] = list(entities_a)
    evidence["entities_b"] = list(entities_b)
    
    # Determine direction
    # Broadening connectors: "arising from", "in connection with", "directly or indirectly"
    broadening_connectors = {
        "arising from", "in connection with", "directly or indirectly",
        "caused by or contributed to", "howsoever caused/arising",
        "any way connected", "related to", "attributable to",
    }
    
    added_broadening = added_connectors & broadening_connectors
    removed_broadening = removed_connectors & broadening_connectors
    
    # Score the change
    scope_score = 0
    
    # Connector changes
    if added_broadening:
        scope_score += len(added_broadening)
    if removed_broadening:
        scope_score -= len(removed_broadening)
    
    # Entity changes (more entities = broader scope)
    scope_score += len(added_entities) * 0.5
    scope_score -= len(removed_entities) * 0.5
    
    # Determine direction
    if scope_score > 0.5:
        direction = DeltaDirection.BROADER
    elif scope_score < -0.5:
        direction = DeltaDirection.NARROWER
    elif details:  # Some change but unclear direction
        direction = DeltaDirection.AMBIGUOUS
    else:
        return None, {}, {}
    
    return direction, details, evidence


def detect_strictness_change(
    dna_a: ClauseDNA,
    dna_b: ClauseDNA,
) -> Tuple[DeltaDirection | None, Dict[str, Any], Dict[str, Any]]:
    """
    Detect strictness changes.
    
    Rules:
    - absolute → conditional: narrower (from insurer perspective)
    - conditional → absolute: broader (from insurer perspective)
    - discretionary involved: ambiguous
    """
    if dna_a.strictness == dna_b.strictness:
        return None, {}, {}
    
    details = {
        "from_strictness": dna_a.strictness.value,
        "to_strictness": dna_b.strictness.value,
    }
    evidence = {
        "strictness_a": dna_a.strictness.value,
        "strictness_b": dna_b.strictness.value,
    }
    
    # Determine direction
    # For exclusions: absolute is stronger exclusion
    # For coverage: absolute is stronger coverage
    # We interpret from coverage perspective:
    # - absolute exclusion → conditional exclusion = broader coverage
    # - conditional exclusion → absolute exclusion = narrower coverage
    
    if dna_a.polarity == Polarity.REMOVE:
        # Exclusion context
        if dna_a.strictness == Strictness.ABSOLUTE and dna_b.strictness == Strictness.CONDITIONAL:
            direction = DeltaDirection.BROADER  # Exclusion weakened
        elif dna_a.strictness == Strictness.CONDITIONAL and dna_b.strictness == Strictness.ABSOLUTE:
            direction = DeltaDirection.NARROWER  # Exclusion strengthened
        elif Strictness.DISCRETIONARY in (dna_a.strictness, dna_b.strictness):
            direction = DeltaDirection.AMBIGUOUS
        else:
            direction = DeltaDirection.AMBIGUOUS
    elif dna_a.polarity == Polarity.GRANT:
        # Coverage grant context
        if dna_a.strictness == Strictness.ABSOLUTE and dna_b.strictness == Strictness.CONDITIONAL:
            direction = DeltaDirection.NARROWER  # Coverage weakened
        elif dna_a.strictness == Strictness.CONDITIONAL and dna_b.strictness == Strictness.ABSOLUTE:
            direction = DeltaDirection.BROADER  # Coverage strengthened
        elif Strictness.DISCRETIONARY in (dna_a.strictness, dna_b.strictness):
            direction = DeltaDirection.AMBIGUOUS
        else:
            direction = DeltaDirection.AMBIGUOUS
    else:
        # Other polarities: discretionary is always ambiguous
        if Strictness.DISCRETIONARY in (dna_a.strictness, dna_b.strictness):
            direction = DeltaDirection.AMBIGUOUS
        else:
            direction = DeltaDirection.NEUTRAL
    
    return direction, details, evidence


def detect_carve_out_change(
    dna_a: ClauseDNA,
    dna_b: ClauseDNA,
) -> Tuple[DeltaDirection | None, Dict[str, Any], Dict[str, Any]]:
    """
    Detect carve-out changes.
    
    Rules:
    - Carve-out removed → broader
    - Carve-out added → narrower
    """
    carve_outs_a = set(dna_a.carve_outs)
    carve_outs_b = set(dna_b.carve_outs)
    
    if carve_outs_a == carve_outs_b:
        return None, {}, {}
    
    added = carve_outs_b - carve_outs_a
    removed = carve_outs_a - carve_outs_b
    
    details: Dict[str, Any] = {}
    if added:
        details["added_carve_outs"] = list(added)
    if removed:
        details["removed_carve_outs"] = list(removed)
    
    evidence = {
        "carve_outs_a": list(carve_outs_a),
        "carve_outs_b": list(carve_outs_b),
    }
    
    # Determine direction based on polarity
    # For exclusions: carve-out is an exception to the exclusion (coverage restored)
    #   - carve-out removed = less coverage (narrower)
    #   - carve-out added = more coverage (broader)
    # For coverage grants: carve-out is an exception to coverage (coverage removed)
    #   - carve-out removed = more coverage (broader)
    #   - carve-out added = less coverage (narrower)
    
    if dna_a.polarity == Polarity.REMOVE:
        # Exclusion context: carve-outs give back coverage
        if removed and not added:
            direction = DeltaDirection.NARROWER  # Lost exception to exclusion
        elif added and not removed:
            direction = DeltaDirection.BROADER  # Gained exception to exclusion
        else:
            direction = DeltaDirection.AMBIGUOUS  # Mixed changes
    else:
        # Coverage/other context: carve-outs take away coverage
        if removed and not added:
            direction = DeltaDirection.BROADER  # Lost exception
        elif added and not removed:
            direction = DeltaDirection.NARROWER  # Gained exception
        else:
            direction = DeltaDirection.AMBIGUOUS  # Mixed changes
    
    return direction, details, evidence


def detect_burden_shift_change(
    dna_a: ClauseDNA,
    dna_b: ClauseDNA,
) -> Tuple[DeltaDirection | None, Dict[str, Any], Dict[str, Any]]:
    """
    Detect burden shift changes.
    
    Rules:
    - false → true: narrower (more obligations on insured)
    - true → false: broader (fewer obligations on insured)
    """
    if dna_a.burden_shift == dna_b.burden_shift:
        return None, {}, {}
    
    details = {
        "from_burden_shift": dna_a.burden_shift,
        "to_burden_shift": dna_b.burden_shift,
    }
    evidence = {
        "burden_shift_a": dna_a.burden_shift,
        "burden_shift_b": dna_b.burden_shift,
    }
    
    if not dna_a.burden_shift and dna_b.burden_shift:
        direction = DeltaDirection.NARROWER  # Added obligations
    else:
        direction = DeltaDirection.BROADER  # Removed obligations
    
    return direction, details, evidence


def detect_numeric_change(
    dna_a: ClauseDNA,
    dna_b: ClauseDNA,
) -> Tuple[DeltaDirection | None, Dict[str, Any], Dict[str, Any]]:
    """
    Detect numeric changes (limits, sublimits, deductibles, waiting periods).
    
    Rules:
    - Higher limit → broader
    - Higher excess/deductible → narrower
    - Longer waiting period → narrower
    """
    numbers_a = dna_a.numbers
    numbers_b = dna_b.numbers
    
    if numbers_a == numbers_b:
        return None, {}, {}
    
    # Check if there are any differences
    all_keys = set(numbers_a.keys()) | set(numbers_b.keys())
    if not all_keys:
        return None, {}, {}
    
    details: Dict[str, Any] = {}
    evidence: Dict[str, Any] = {
        "numbers_a": numbers_a,
        "numbers_b": numbers_b,
    }
    
    direction_signals: List[str] = []
    
    # Limits - higher is broader
    for key in ["limits", "sublimits", "amounts"]:
        vals_a = numbers_a.get(key, [])
        vals_b = numbers_b.get(key, [])
        if vals_a or vals_b:
            max_a = max(vals_a) if vals_a else 0
            max_b = max(vals_b) if vals_b else 0
            if max_b > max_a:
                details[f"{key}_increased"] = {"from": max_a, "to": max_b}
                direction_signals.append("broader")
            elif max_b < max_a:
                details[f"{key}_decreased"] = {"from": max_a, "to": max_b}
                direction_signals.append("narrower")
    
    # Deductibles/excess - higher is narrower
    for key in ["deductibles"]:
        vals_a = numbers_a.get(key, [])
        vals_b = numbers_b.get(key, [])
        if vals_a or vals_b:
            max_a = max(vals_a) if vals_a else 0
            max_b = max(vals_b) if vals_b else 0
            if max_b > max_a:
                details[f"{key}_increased"] = {"from": max_a, "to": max_b}
                direction_signals.append("narrower")
            elif max_b < max_a:
                details[f"{key}_decreased"] = {"from": max_a, "to": max_b}
                direction_signals.append("broader")
    
    # Waiting periods - longer is narrower
    for key in ["waiting_period_days", "waiting_period_hours", "time_days", "time_hours"]:
        vals_a = numbers_a.get(key, [])
        vals_b = numbers_b.get(key, [])
        if vals_a or vals_b:
            max_a = max(vals_a) if vals_a else 0
            max_b = max(vals_b) if vals_b else 0
            if max_b > max_a:
                details[f"{key}_increased"] = {"from": max_a, "to": max_b}
                if "waiting" in key:
                    direction_signals.append("narrower")
            elif max_b < max_a:
                details[f"{key}_decreased"] = {"from": max_a, "to": max_b}
                if "waiting" in key:
                    direction_signals.append("broader")
    
    # Percentages
    pcts_a = numbers_a.get("percentages", [])
    pcts_b = numbers_b.get("percentages", [])
    if pcts_a or pcts_b:
        max_a = max(pcts_a) if pcts_a else 0
        max_b = max(pcts_b) if pcts_b else 0
        if max_b != max_a:
            details["percentage_changed"] = {"from": max_a, "to": max_b}
            # Direction depends on context - mark as ambiguous
            direction_signals.append("ambiguous")
    
    if not details:
        return None, {}, {}
    
    # Determine overall direction
    broader_count = direction_signals.count("broader")
    narrower_count = direction_signals.count("narrower")
    ambiguous_count = direction_signals.count("ambiguous")
    
    if broader_count > 0 and narrower_count == 0 and ambiguous_count == 0:
        direction = DeltaDirection.BROADER
    elif narrower_count > 0 and broader_count == 0 and ambiguous_count == 0:
        direction = DeltaDirection.NARROWER
    elif broader_count == narrower_count and broader_count > 0:
        direction = DeltaDirection.NEUTRAL  # Balanced changes
    else:
        direction = DeltaDirection.AMBIGUOUS
    
    return direction, details, evidence


def detect_definition_dependency_change(
    dna_a: ClauseDNA,
    dna_b: ClauseDNA,
) -> Tuple[DeltaDirection | None, Dict[str, Any], Dict[str, Any]]:
    """
    Detect definition dependency changes.
    
    Rules:
    - New dependency introduced → ambiguous
    - Dependency removed → ambiguous
    (No inference beyond flagging.)
    """
    deps_a = set(dna_a.definition_dependencies)
    deps_b = set(dna_b.definition_dependencies)
    
    if deps_a == deps_b:
        return None, {}, {}
    
    added = deps_b - deps_a
    removed = deps_a - deps_b
    
    details: Dict[str, Any] = {}
    if added:
        details["added_dependencies"] = list(added)
    if removed:
        details["removed_dependencies"] = list(removed)
    
    evidence = {
        "dependencies_a": list(deps_a),
        "dependencies_b": list(deps_b),
    }
    
    # Always ambiguous - we don't know what the definition change means
    direction = DeltaDirection.AMBIGUOUS
    
    return direction, details, evidence


def detect_temporal_change(
    dna_a: ClauseDNA,
    dna_b: ClauseDNA,
) -> Tuple[DeltaDirection | None, Dict[str, Any], Dict[str, Any]]:
    """
    Detect temporal constraint changes.
    
    Rules:
    - Additional timing constraint → narrower
    - Constraint removed → broader
    """
    constraints_a = set(dna_a.temporal_constraints)
    constraints_b = set(dna_b.temporal_constraints)
    
    if constraints_a == constraints_b:
        return None, {}, {}
    
    added = constraints_b - constraints_a
    removed = constraints_a - constraints_b
    
    details: Dict[str, Any] = {}
    if added:
        details["added_constraints"] = list(added)
    if removed:
        details["removed_constraints"] = list(removed)
    
    evidence = {
        "constraints_a": list(constraints_a),
        "constraints_b": list(constraints_b),
    }
    
    # Determine direction
    if added and not removed:
        direction = DeltaDirection.NARROWER  # More constraints
    elif removed and not added:
        direction = DeltaDirection.BROADER  # Fewer constraints
    else:
        direction = DeltaDirection.AMBIGUOUS  # Mixed changes
    
    return direction, details, evidence


# ---------------------------------------------------------------------------
# Delta Detection Orchestration
# ---------------------------------------------------------------------------


@dataclass
class _DetectionResult:
    """Result of a single delta detection function."""
    delta_type: DeltaType
    direction: DeltaDirection | None
    details: Dict[str, Any]
    evidence: Dict[str, Any]


def _detect_all_deltas(
    dna_a: ClauseDNA,
    dna_b: ClauseDNA,
) -> List[_DetectionResult]:
    """Run all delta detection functions."""
    results: List[_DetectionResult] = []
    
    # 1. Scope change
    direction, details, evidence = detect_scope_change(dna_a, dna_b)
    if direction is not None:
        results.append(_DetectionResult(
            delta_type=DeltaType.SCOPE_CHANGE,
            direction=direction,
            details=details,
            evidence=evidence,
        ))
    
    # 2. Strictness change
    direction, details, evidence = detect_strictness_change(dna_a, dna_b)
    if direction is not None:
        results.append(_DetectionResult(
            delta_type=DeltaType.STRICTNESS_CHANGE,
            direction=direction,
            details=details,
            evidence=evidence,
        ))
    
    # 3. Carve-out change
    direction, details, evidence = detect_carve_out_change(dna_a, dna_b)
    if direction is not None:
        results.append(_DetectionResult(
            delta_type=DeltaType.CARVE_OUT_CHANGE,
            direction=direction,
            details=details,
            evidence=evidence,
        ))
    
    # 4. Burden shift change
    direction, details, evidence = detect_burden_shift_change(dna_a, dna_b)
    if direction is not None:
        results.append(_DetectionResult(
            delta_type=DeltaType.BURDEN_SHIFT_CHANGE,
            direction=direction,
            details=details,
            evidence=evidence,
        ))
    
    # 5. Numeric change
    direction, details, evidence = detect_numeric_change(dna_a, dna_b)
    if direction is not None:
        results.append(_DetectionResult(
            delta_type=DeltaType.NUMERIC_CHANGE,
            direction=direction,
            details=details,
            evidence=evidence,
        ))
    
    # 6. Definition dependency change
    direction, details, evidence = detect_definition_dependency_change(dna_a, dna_b)
    if direction is not None:
        results.append(_DetectionResult(
            delta_type=DeltaType.DEFINITION_DEPENDENCY_CHANGE,
            direction=direction,
            details=details,
            evidence=evidence,
        ))
    
    # 7. Temporal change
    direction, details, evidence = detect_temporal_change(dna_a, dna_b)
    if direction is not None:
        results.append(_DetectionResult(
            delta_type=DeltaType.TEMPORAL_CHANGE,
            direction=direction,
            details=details,
            evidence=evidence,
        ))
    
    return results


def _calculate_confidence(
    alignment_confidence: float,
    dna_a_confidence: float,
    dna_b_confidence: float,
    detection_results: List[_DetectionResult],
) -> float:
    """
    Calculate confidence for the delta detection.
    
    Start at min(alignment.confidence, dna.confidence_A, dna.confidence_B)
    Reduce if conflicting signals exist.
    """
    base_confidence = min(alignment_confidence, dna_a_confidence, dna_b_confidence)
    
    # Check for conflicting signals
    directions = [r.direction for r in detection_results if r.direction]
    
    if not directions:
        return base_confidence
    
    broader_count = sum(1 for d in directions if d == DeltaDirection.BROADER)
    narrower_count = sum(1 for d in directions if d == DeltaDirection.NARROWER)
    ambiguous_count = sum(1 for d in directions if d == DeltaDirection.AMBIGUOUS)
    
    # Reduce confidence for conflicts
    if broader_count > 0 and narrower_count > 0:
        # Conflicting directions
        base_confidence *= 0.8
    
    if ambiguous_count > 0:
        # Some ambiguous results
        base_confidence *= 0.9
    
    return round(max(0.1, min(1.0, base_confidence)), 4)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_delta_interpretation(
    doc_id_a: str,
    doc_id_b: str,
) -> DeltaResult:
    """
    Run the Delta Interpretation Agent on aligned clause pairs.
    
    Args:
        doc_id_a: First document ID
        doc_id_b: Second document ID
    
    Returns:
        DeltaResult containing all detected deltas.
    """
    # Load alignments from Segment 5
    alignment_store = AlignmentStore()
    alignments = alignment_store.get_alignments(doc_id_a, doc_id_b)
    
    # Load DNA from Segment 4
    dna_store = DNAStore()
    dna_a_all = dna_store.get_all_dna(doc_id_a)
    dna_b_all = dna_store.get_all_dna(doc_id_b)
    
    dna_a_map = {d.block_id: d for d in dna_a_all}
    dna_b_map = {d.block_id: d for d in dna_b_all}
    
    # Process each aligned pair
    all_deltas: List[ClauseDelta] = []
    stats: Dict[str, int] = {
        "total_alignments": len(alignments),
        "matched_alignments": 0,
        "total_deltas": 0,
        "broader": 0,
        "narrower": 0,
        "neutral": 0,
        "ambiguous": 0,
    }
    
    for alignment in alignments:
        # Skip unmatched
        if alignment.alignment_type == AlignmentType.UNMATCHED:
            continue
        if not alignment.block_id_b:
            continue
        
        stats["matched_alignments"] += 1
        
        # Get DNA for both sides
        dna_a = dna_a_map.get(alignment.block_id_a)
        dna_b = dna_b_map.get(alignment.block_id_b)
        
        if not dna_a or not dna_b:
            continue
        
        # Detect all deltas
        detection_results = _detect_all_deltas(dna_a, dna_b)
        
        if not detection_results:
            continue
        
        # Calculate confidence
        confidence = _calculate_confidence(
            alignment.confidence,
            dna_a.confidence,
            dna_b.confidence,
            detection_results,
        )
        
        # Create delta objects
        for result in detection_results:
            delta = ClauseDelta(
                doc_id_a=doc_id_a,
                block_id_a=alignment.block_id_a,
                doc_id_b=doc_id_b,
                block_id_b=alignment.block_id_b,
                clause_type=alignment.clause_type,
                delta_type=result.delta_type,
                direction=result.direction,
                details=result.details,
                evidence=result.evidence,
                confidence=confidence,
            )
            all_deltas.append(delta)
            
            stats["total_deltas"] += 1
            if result.direction == DeltaDirection.BROADER:
                stats["broader"] += 1
            elif result.direction == DeltaDirection.NARROWER:
                stats["narrower"] += 1
            elif result.direction == DeltaDirection.NEUTRAL:
                stats["neutral"] += 1
            else:
                stats["ambiguous"] += 1
    
    # Persist
    delta_store = DeltaStore()
    delta_store.clear_deltas(doc_id_a, doc_id_b)
    delta_store.persist_deltas(all_deltas)
    
    return DeltaResult(
        doc_id_a=doc_id_a,
        doc_id_b=doc_id_b,
        deltas=all_deltas,
        stats=stats,
    )


def get_deltas(doc_id_a: str, doc_id_b: str) -> List[ClauseDelta]:
    """Retrieve all deltas for a document pair."""
    store = DeltaStore()
    return store.get_deltas(doc_id_a, doc_id_b)


def get_deltas_for_clause(block_id_a: str) -> List[ClauseDelta]:
    """Retrieve all deltas for a specific clause from document A."""
    store = DeltaStore()
    return store.get_deltas_for_clause(block_id_a)
