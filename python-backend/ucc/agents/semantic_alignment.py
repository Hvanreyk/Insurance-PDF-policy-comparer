"""Segment 5: Semantic Alignment Agent (Like-to-Like Clause Matching).

Aligns like-to-like clauses across two policy documents in a way that reflects
legal intent, not superficial wording similarity.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Set, Tuple

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from ..storage.alignment_store import (
    AlignmentResult,
    AlignmentStore,
    AlignmentType,
    ClauseAlignment,
)
from ..storage.classification_store import ClassificationStore, ClauseType
from ..storage.definitions_store import DefinitionsStore
from ..storage.dna_store import ClauseDNA, DNAStore, Polarity, Strictness
from ..storage.layout_store import LayoutStore


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Alignment score weights
WEIGHT_DNA_SIMILARITY = 0.45
WEIGHT_SEMANTIC_SIMILARITY = 0.30
WEIGHT_SECTION_SIMILARITY = 0.25

# DNA feature weights (for weighted Jaccard)
DNA_FEATURE_WEIGHTS: Dict[str, float] = {
    "polarity": 0.20,
    "strictness": 0.20,
    "scope_connectors": 0.15,
    "entities": 0.15,
    "carve_outs": 0.10,
    "definition_dependencies": 0.10,
    "temporal_constraints": 0.10,
}

# Thresholds
MIN_ALIGNMENT_THRESHOLD = 0.6
ONE_TO_MANY_THRESHOLD = 0.85
LENGTH_RATIO_MIN = 0.5
LENGTH_RATIO_MAX = 2.0

# Penalties
CARVE_OUT_DIFF_PENALTY = 0.10
BURDEN_SHIFT_DIFF_PENALTY = 0.08


# ---------------------------------------------------------------------------
# Helper Classes
# ---------------------------------------------------------------------------

@dataclass
class CandidatePair:
    """A candidate alignment pair."""

    block_id_a: str
    block_id_b: str
    clause_type: str
    text_a: str
    text_b: str
    expanded_text_a: str
    expanded_text_b: str
    dna_a: ClauseDNA
    dna_b: ClauseDNA
    section_path_a: List[str]
    section_path_b: List[str]


@dataclass
class ScoredCandidate:
    """A candidate with computed scores."""

    pair: CandidatePair
    section_similarity: float
    dna_similarity: float
    semantic_similarity: float
    alignment_score: float
    confidence: float
    penalties: List[str]


# ---------------------------------------------------------------------------
# Similarity Functions
# ---------------------------------------------------------------------------


def _tokenize_section_path(section_path: List[str]) -> Set[str]:
    """Tokenize a section path into lowercase words."""
    tokens: Set[str] = set()
    for part in section_path:
        for word in part.lower().split():
            if len(word) > 2:  # Skip very short words
                tokens.add(word)
    return tokens


def compute_section_similarity(
    section_path_a: List[str],
    section_path_b: List[str],
) -> float:
    """
    Compute similarity between section paths using token overlap
    with depth weighting.
    """
    if not section_path_a and not section_path_b:
        return 1.0  # Both empty = same context
    if not section_path_a or not section_path_b:
        return 0.3  # One empty = partial match
    
    # Token overlap (Jaccard)
    tokens_a = _tokenize_section_path(section_path_a)
    tokens_b = _tokenize_section_path(section_path_b)
    
    if not tokens_a and not tokens_b:
        return 1.0
    if not tokens_a or not tokens_b:
        return 0.3
    
    intersection = len(tokens_a & tokens_b)
    union = len(tokens_a | tokens_b)
    token_similarity = intersection / union if union > 0 else 0.0
    
    # Depth weighting: shared deeper paths score higher
    min_depth = min(len(section_path_a), len(section_path_b))
    max_depth = max(len(section_path_a), len(section_path_b))
    
    shared_depth = 0
    for i in range(min_depth):
        if section_path_a[i].lower() == section_path_b[i].lower():
            shared_depth = i + 1
        else:
            break
    
    depth_bonus = (shared_depth / max_depth) * 0.3 if max_depth > 0 else 0.0
    
    return min(token_similarity + depth_bonus, 1.0)


def _set_similarity(set_a: Set[str], set_b: Set[str]) -> float:
    """Compute Jaccard similarity between two sets."""
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


def _list_similarity(list_a: List[str], list_b: List[str]) -> float:
    """Compute similarity between two lists (as sets)."""
    return _set_similarity(set(list_a), set(list_b))


def compute_dna_similarity(dna_a: ClauseDNA, dna_b: ClauseDNA) -> Tuple[float, Dict[str, float]]:
    """
    Compute weighted similarity across DNA features.
    
    Returns (similarity_score, component_scores).
    """
    components: Dict[str, float] = {}
    
    # Polarity (exact match)
    components["polarity"] = 1.0 if dna_a.polarity == dna_b.polarity else 0.0
    
    # Strictness (exact match with partial credit)
    if dna_a.strictness == dna_b.strictness:
        components["strictness"] = 1.0
    elif {dna_a.strictness, dna_b.strictness} == {Strictness.CONDITIONAL, Strictness.DISCRETIONARY}:
        components["strictness"] = 0.5  # Partial match
    else:
        components["strictness"] = 0.0
    
    # Scope connectors (set similarity)
    components["scope_connectors"] = _list_similarity(
        dna_a.scope_connectors, dna_b.scope_connectors
    )
    
    # Entities (set similarity)
    components["entities"] = _list_similarity(dna_a.entities, dna_b.entities)
    
    # Carve-outs (set similarity on normalized carve-outs)
    # Normalize by extracting the trigger word
    carve_a = {c.split(":")[0].strip().lower() for c in dna_a.carve_outs}
    carve_b = {c.split(":")[0].strip().lower() for c in dna_b.carve_outs}
    components["carve_outs"] = _set_similarity(carve_a, carve_b)
    
    # Definition dependencies (set similarity)
    components["definition_dependencies"] = _list_similarity(
        dna_a.definition_dependencies, dna_b.definition_dependencies
    )
    
    # Temporal constraints (set similarity)
    components["temporal_constraints"] = _list_similarity(
        dna_a.temporal_constraints, dna_b.temporal_constraints
    )
    
    # Weighted sum
    total_weight = sum(DNA_FEATURE_WEIGHTS.values())
    weighted_sum = sum(
        components[feature] * weight
        for feature, weight in DNA_FEATURE_WEIGHTS.items()
    )
    similarity = weighted_sum / total_weight if total_weight > 0 else 0.0
    
    return similarity, components


def compute_semantic_similarity(
    texts_a: List[str],
    texts_b: List[str],
) -> np.ndarray:
    """
    Compute cosine similarity matrix between two sets of texts
    using TF-IDF embeddings.
    
    Returns a matrix of shape (len(texts_a), len(texts_b)).
    """
    if not texts_a or not texts_b:
        return np.zeros((len(texts_a) if texts_a else 0, len(texts_b) if texts_b else 0))
    
    # Combine for fitting
    all_texts = texts_a + texts_b
    
    vectorizer = TfidfVectorizer(
        stop_words="english",
        ngram_range=(1, 2),
        max_features=5000,
    )
    
    try:
        tfidf_matrix = vectorizer.fit_transform(all_texts)
    except ValueError:
        # Empty vocabulary (all stop words)
        return np.zeros((len(texts_a), len(texts_b)))
    
    matrix_a = tfidf_matrix[:len(texts_a)]
    matrix_b = tfidf_matrix[len(texts_a):]
    
    return cosine_similarity(matrix_a, matrix_b)


def compute_alignment_score(
    section_similarity: float,
    dna_similarity: float,
    semantic_similarity: float,
    dna_a: ClauseDNA,
    dna_b: ClauseDNA,
) -> Tuple[float, float, List[str]]:
    """
    Compute the combined alignment score with penalties.
    
    Returns (alignment_score, confidence, penalty_notes).
    """
    # Base score
    score = (
        WEIGHT_DNA_SIMILARITY * dna_similarity +
        WEIGHT_SEMANTIC_SIMILARITY * semantic_similarity +
        WEIGHT_SECTION_SIMILARITY * section_similarity
    )
    
    penalties: List[str] = []
    
    # Penalty: carve-outs differ materially
    if dna_a.carve_outs or dna_b.carve_outs:
        carve_a = set(dna_a.carve_outs)
        carve_b = set(dna_b.carve_outs)
        if carve_a != carve_b:
            # Check if they're materially different (not just wording)
            carve_a_triggers = {c.split(":")[0].strip().lower() for c in carve_a}
            carve_b_triggers = {c.split(":")[0].strip().lower() for c in carve_b}
            if carve_a_triggers != carve_b_triggers:
                score -= CARVE_OUT_DIFF_PENALTY
                penalties.append(f"carve_out_diff (-{CARVE_OUT_DIFF_PENALTY})")
    
    # Penalty: burden_shift differs
    if dna_a.burden_shift != dna_b.burden_shift:
        score -= BURDEN_SHIFT_DIFF_PENALTY
        penalties.append(f"burden_shift_diff (-{BURDEN_SHIFT_DIFF_PENALTY})")
    
    # Ensure score is in [0, 1]
    score = max(0.0, min(1.0, score))
    
    # Confidence based on agreement across components
    component_agreement = (
        (1.0 if dna_a.polarity == dna_b.polarity else 0.5) +
        (1.0 if dna_a.strictness == dna_b.strictness else 0.5) +
        (1.0 if section_similarity > 0.7 else 0.5)
    ) / 3.0
    
    confidence = score * component_agreement
    
    return score, confidence, penalties


# ---------------------------------------------------------------------------
# Candidate Filtering
# ---------------------------------------------------------------------------


def filter_candidates(
    blocks_a: List[Dict[str, Any]],
    blocks_b: List[Dict[str, Any]],
    classifications_a: Dict[str, str],
    classifications_b: Dict[str, str],
) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
    """
    Filter candidate pairs based on hard constraints:
    - Same clause type
    - Neither is ADMIN
    - Length ratio in [0.5, 2.0]
    """
    candidates: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
    
    for block_a in blocks_a:
        type_a = classifications_a.get(block_a["id"], "UNCERTAIN")
        
        # Skip ADMIN
        if type_a == ClauseType.ADMIN.value:
            continue
        
        len_a = len(block_a.get("text", ""))
        if len_a == 0:
            continue
        
        for block_b in blocks_b:
            type_b = classifications_b.get(block_b["id"], "UNCERTAIN")
            
            # Must match clause type
            if type_a != type_b:
                continue
            
            # Skip ADMIN
            if type_b == ClauseType.ADMIN.value:
                continue
            
            len_b = len(block_b.get("text", ""))
            if len_b == 0:
                continue
            
            # Length ratio constraint
            ratio = len_a / len_b
            if ratio < LENGTH_RATIO_MIN or ratio > LENGTH_RATIO_MAX:
                continue
            
            candidates.append((block_a, block_b))
    
    return candidates


# ---------------------------------------------------------------------------
# Bipartite Matching
# ---------------------------------------------------------------------------


def bipartite_match(
    scored_candidates: List[ScoredCandidate],
    threshold: float = MIN_ALIGNMENT_THRESHOLD,
    one_to_many_threshold: float = ONE_TO_MANY_THRESHOLD,
) -> List[ScoredCandidate]:
    """
    Perform greedy bipartite matching to maximize total alignment score.
    
    Prevents multiple matches for the same clause unless score >= one_to_many_threshold.
    """
    # Sort by score descending
    sorted_candidates = sorted(
        scored_candidates,
        key=lambda c: c.alignment_score,
        reverse=True,
    )
    
    matched: List[ScoredCandidate] = []
    matched_a: Set[str] = set()
    matched_b: Set[str] = set()
    
    for candidate in sorted_candidates:
        block_id_a = candidate.pair.block_id_a
        block_id_b = candidate.pair.block_id_b
        
        # Skip if below threshold
        if candidate.alignment_score < threshold:
            continue
        
        # Check if already matched
        a_matched = block_id_a in matched_a
        b_matched = block_id_b in matched_b
        
        if a_matched and b_matched:
            continue
        
        # Allow one-to-many if score is very high and section paths match
        if a_matched or b_matched:
            if candidate.alignment_score >= one_to_many_threshold:
                # Check if section paths are identical
                if candidate.pair.section_path_a == candidate.pair.section_path_b:
                    # Allow one-to-many
                    matched.append(candidate)
                    matched_a.add(block_id_a)
                    matched_b.add(block_id_b)
            continue
        
        # Standard one-to-one match
        matched.append(candidate)
        matched_a.add(block_id_a)
        matched_b.add(block_id_b)
    
    return matched


# ---------------------------------------------------------------------------
# Main Alignment Function
# ---------------------------------------------------------------------------


def _load_document_data(doc_id: str) -> Tuple[
    List[Dict[str, Any]],
    Dict[str, str],
    Dict[str, ClauseDNA],
    Dict[str, str],
]:
    """Load all required data for a document."""
    layout_store = LayoutStore()
    classification_store = ClassificationStore()
    dna_store = DNAStore()
    definitions_store = DefinitionsStore()
    
    # Load blocks
    blocks = layout_store.get_blocks(doc_id)
    blocks_data = [
        {
            "id": b.id,
            "text": b.text,
            "section_path": b.section_path,
        }
        for b in blocks
    ]
    
    # Load classifications
    classifications = classification_store.get_all_classifications(doc_id)
    classifications_map = {c.block_id: c.clause_type.value for c in classifications}
    
    # Load DNA
    dna_records = dna_store.get_all_dna(doc_id)
    dna_map = {d.block_id: d for d in dna_records}
    
    # Load expanded text
    expansions = definitions_store.get_all_expansions(doc_id)
    expanded_map = {e.block_id: e.expanded_text for e in expansions}
    
    return blocks_data, classifications_map, dna_map, expanded_map


def run_semantic_alignment(
    doc_id_a: str,
    doc_id_b: str,
) -> AlignmentResult:
    """
    Run the Semantic Alignment Agent on two documents.
    
    Args:
        doc_id_a: First document ID
        doc_id_b: Second document ID
    
    Returns:
        AlignmentResult containing all clause alignments.
    
    Raises:
        ValueError: If no blocks found for either document.
    """
    # #region agent log
    import json as _json, time as _time, os as _os
    _log_path = "/Users/hudsonvanreyk/Desktop/Insurance Comparator/Insurance-PDF-policy-comparer/.cursor/debug.log"
    def _dbg(loc, msg, data=None, hyp=""):
        try:
            _os.makedirs(_os.path.dirname(_log_path), exist_ok=True)
            with open(_log_path, "a") as _f:
                _f.write(_json.dumps({"location": loc, "message": msg, "data": data or {}, "hypothesisId": hyp, "timestamp": int(_time.time()*1000)}) + "\n")
        except Exception as _e:
            print(f"[DEBUG LOG ERROR] {_e}")
    _dbg("semantic_alignment.py:entry", "run_semantic_alignment ENTERED", {"doc_id_a": doc_id_a, "doc_id_b": doc_id_b}, "H1")
    # #endregion
    
    # Load data for both documents
    blocks_a, classifications_a, dna_map_a, expanded_map_a = _load_document_data(doc_id_a)
    blocks_b, classifications_b, dna_map_b, expanded_map_b = _load_document_data(doc_id_b)
    
    # #region agent log
    _dbg("semantic_alignment.py:after_load", "Data loaded", {
        "blocks_a": len(blocks_a), "blocks_b": len(blocks_b),
        "classifications_a": len(classifications_a), "classifications_b": len(classifications_b),
        "dna_map_a": len(dna_map_a), "dna_map_b": len(dna_map_b),
        "expanded_map_a": len(expanded_map_a), "expanded_map_b": len(expanded_map_b),
        "sample_block_ids_a": [b["id"] for b in blocks_a[:3]],
        "sample_clf_keys_a": list(classifications_a.keys())[:3],
        "sample_dna_keys_a": list(dna_map_a.keys())[:3],
        "clf_type_counts_a": {},
        "clf_type_counts_b": {},
    }, "H1")
    # Count classification types
    from collections import Counter
    _type_counts_a = Counter(classifications_a.values())
    _type_counts_b = Counter(classifications_b.values())
    _unclassified_a = len(blocks_a) - len(classifications_a)
    _unclassified_b = len(blocks_b) - len(classifications_b)
    _dbg("semantic_alignment.py:clf_types", "Classification type distributions", {
        "type_counts_a": dict(_type_counts_a), "type_counts_b": dict(_type_counts_b),
        "unclassified_a": _unclassified_a, "unclassified_b": _unclassified_b,
    }, "H1")
    # #endregion
    
    if not blocks_a:
        raise ValueError(f"No blocks found for doc_id_a: {doc_id_a}")
    if not blocks_b:
        raise ValueError(f"No blocks found for doc_id_b: {doc_id_b}")
    
    # Filter candidates
    # #region agent log
    _t_filter = _time.time()
    # #endregion
    candidate_pairs = filter_candidates(
        blocks_a, blocks_b, classifications_a, classifications_b
    )
    # #region agent log
    _dbg("semantic_alignment.py:after_filter", "filter_candidates complete", {
        "candidate_pair_count": len(candidate_pairs),
        "elapsed_s": round(_time.time() - _t_filter, 3),
    }, "H2")
    # #endregion
    
    if not candidate_pairs:
        # No valid candidates - all blocks are unmatched
        # #region agent log
        _dbg("semantic_alignment.py:no_candidates", "No candidate pairs - creating unmatched", {}, "H2")
        # #endregion
        alignments = _create_unmatched_alignments(
            doc_id_a, doc_id_b, blocks_a, classifications_a, dna_map_a
        )
        store = AlignmentStore()
        store.clear_alignments(doc_id_a, doc_id_b)
        store.persist_alignments(alignments)
        return AlignmentResult(
            doc_id_a=doc_id_a,
            doc_id_b=doc_id_b,
            alignments=alignments,
            stats={"total": len(alignments), "matched": 0, "unmatched": len(alignments)},
        )
    
    # Build candidate pairs with all required data
    candidates: List[CandidatePair] = []
    # #region agent log
    _dna_miss_a = 0
    _dna_miss_b = 0
    # #endregion
    for block_a, block_b in candidate_pairs:
        dna_a = dna_map_a.get(block_a["id"])
        dna_b = dna_map_b.get(block_b["id"])
        
        if not dna_a or not dna_b:
            # #region agent log
            if not dna_a: _dna_miss_a += 1
            if not dna_b: _dna_miss_b += 1
            # #endregion
            continue
        
        expanded_a = expanded_map_a.get(block_a["id"], block_a["text"])
        expanded_b = expanded_map_b.get(block_b["id"], block_b["text"])
        
        candidates.append(CandidatePair(
            block_id_a=block_a["id"],
            block_id_b=block_b["id"],
            clause_type=classifications_a.get(block_a["id"], "UNCERTAIN"),
            text_a=block_a["text"],
            text_b=block_b["text"],
            expanded_text_a=expanded_a,
            expanded_text_b=expanded_b,
            dna_a=dna_a,
            dna_b=dna_b,
            section_path_a=block_a.get("section_path", []),
            section_path_b=block_b.get("section_path", []),
        ))
    
    # #region agent log
    _dbg("semantic_alignment.py:after_build_candidates", "CandidatePair objects built", {
        "candidate_pairs_in": len(candidate_pairs),
        "candidates_with_dna": len(candidates),
        "dna_miss_a": _dna_miss_a,
        "dna_miss_b": _dna_miss_b,
    }, "H1")
    # #endregion
    
    if not candidates:
        # #region agent log
        _dbg("semantic_alignment.py:no_candidates_dna", "No candidates after DNA filter", {}, "H1")
        # #endregion
        alignments = _create_unmatched_alignments(
            doc_id_a, doc_id_b, blocks_a, classifications_a, dna_map_a
        )
        store = AlignmentStore()
        store.clear_alignments(doc_id_a, doc_id_b)
        store.persist_alignments(alignments)
        return AlignmentResult(
            doc_id_a=doc_id_a,
            doc_id_b=doc_id_b,
            alignments=alignments,
            stats={"total": len(alignments), "matched": 0, "unmatched": len(alignments)},
        )
    
    # Compute semantic similarity matrix
    texts_a = [c.expanded_text_a for c in candidates]
    texts_b = [c.expanded_text_b for c in candidates]
    
    # Get unique texts for efficiency
    unique_texts_a = list(dict.fromkeys(texts_a))
    unique_texts_b = list(dict.fromkeys(texts_b))
    
    # #region agent log
    _dbg("semantic_alignment.py:before_tfidf", "About to compute TF-IDF similarity", {
        "unique_texts_a": len(unique_texts_a), "unique_texts_b": len(unique_texts_b),
        "total_candidates": len(candidates),
    }, "H2")
    _t_sim = _time.time()
    # #endregion
    
    sim_matrix = compute_semantic_similarity(unique_texts_a, unique_texts_b)
    
    # #region agent log
    _dbg("semantic_alignment.py:after_tfidf", "TF-IDF similarity computed", {
        "elapsed_s": round(_time.time() - _t_sim, 3),
        "matrix_shape": list(sim_matrix.shape) if hasattr(sim_matrix, 'shape') else "unknown",
    }, "H2")
    # #endregion
    
    # Build index maps
    text_to_idx_a = {t: i for i, t in enumerate(unique_texts_a)}
    text_to_idx_b = {t: i for i, t in enumerate(unique_texts_b)}
    
    # Score all candidates
    scored_candidates: List[ScoredCandidate] = []
    
    # #region agent log
    _t_score = _time.time()
    # #endregion
    
    for candidate in candidates:
        # Section similarity
        section_sim = compute_section_similarity(
            candidate.section_path_a, candidate.section_path_b
        )
        
        # DNA similarity
        dna_sim, dna_components = compute_dna_similarity(
            candidate.dna_a, candidate.dna_b
        )
        
        # Semantic similarity
        idx_a = text_to_idx_a.get(candidate.expanded_text_a, 0)
        idx_b = text_to_idx_b.get(candidate.expanded_text_b, 0)
        semantic_sim = float(sim_matrix[idx_a, idx_b]) if sim_matrix.size > 0 else 0.0
        
        # Combined score
        alignment_score, confidence, penalties = compute_alignment_score(
            section_sim, dna_sim, semantic_sim, candidate.dna_a, candidate.dna_b
        )
        
        scored_candidates.append(ScoredCandidate(
            pair=candidate,
            section_similarity=section_sim,
            dna_similarity=dna_sim,
            semantic_similarity=semantic_sim,
            alignment_score=alignment_score,
            confidence=confidence,
            penalties=penalties,
        ))
    
    # #region agent log
    _dbg("semantic_alignment.py:after_scoring", "All candidates scored", {
        "scored_count": len(scored_candidates),
        "elapsed_s": round(_time.time() - _t_score, 3),
    }, "H2")
    # #endregion
    
    # Perform bipartite matching
    # #region agent log
    _t_match = _time.time()
    # #endregion
    matched = bipartite_match(scored_candidates)
    matched_block_ids_a = {m.pair.block_id_a for m in matched}
    # #region agent log
    _dbg("semantic_alignment.py:after_bipartite", "Bipartite matching done", {
        "matched_count": len(matched),
        "elapsed_s": round(_time.time() - _t_match, 3),
    }, "H2")
    # #endregion
    
    # Create alignments
    alignments: List[ClauseAlignment] = []
    
    for scored in matched:
        # Determine alignment type
        alignment_type = AlignmentType.ONE_TO_ONE
        
        alignments.append(ClauseAlignment(
            doc_id_a=doc_id_a,
            block_id_a=scored.pair.block_id_a,
            doc_id_b=doc_id_b,
            block_id_b=scored.pair.block_id_b,
            clause_type=scored.pair.clause_type,
            alignment_score=round(scored.alignment_score, 4),
            score_components={
                "section_similarity": round(scored.section_similarity, 4),
                "dna_similarity": round(scored.dna_similarity, 4),
                "semantic_similarity": round(scored.semantic_similarity, 4),
            },
            confidence=round(scored.confidence, 4),
            alignment_type=alignment_type,
            notes="; ".join(scored.penalties) if scored.penalties else "",
        ))
    
    # Add unmatched blocks from document A
    for block in blocks_a:
        if block["id"] not in matched_block_ids_a:
            clause_type = classifications_a.get(block["id"], "UNCERTAIN")
            if clause_type == ClauseType.ADMIN.value:
                continue
            
            dna = dna_map_a.get(block["id"])
            confidence = dna.confidence if dna else 0.0
            
            alignments.append(ClauseAlignment(
                doc_id_a=doc_id_a,
                block_id_a=block["id"],
                doc_id_b=doc_id_b,
                block_id_b=None,
                clause_type=clause_type,
                alignment_score=0.0,
                score_components={},
                confidence=confidence,
                alignment_type=AlignmentType.UNMATCHED,
                notes="No matching clause found in document B",
            ))
    
    # Stats
    matched_count = sum(1 for a in alignments if a.alignment_type != AlignmentType.UNMATCHED)
    unmatched_count = sum(1 for a in alignments if a.alignment_type == AlignmentType.UNMATCHED)
    
    stats = {
        "total": len(alignments),
        "matched": matched_count,
        "unmatched": unmatched_count,
        "avg_score": round(
            sum(a.alignment_score for a in alignments if a.alignment_type != AlignmentType.UNMATCHED)
            / matched_count if matched_count > 0 else 0.0,
            4
        ),
    }
    
    # Persist
    store = AlignmentStore()
    store.clear_alignments(doc_id_a, doc_id_b)
    store.persist_alignments(alignments)
    
    # #region agent log
    _dbg("semantic_alignment.py:returning", "run_semantic_alignment RETURNING", {
        "alignment_count": len(alignments),
        "stats": stats,
    }, "H5")
    # #endregion
    
    return AlignmentResult(
        doc_id_a=doc_id_a,
        doc_id_b=doc_id_b,
        alignments=alignments,
        stats=stats,
    )


def _create_unmatched_alignments(
    doc_id_a: str,
    doc_id_b: str,
    blocks_a: List[Dict[str, Any]],
    classifications_a: Dict[str, str],
    dna_map_a: Dict[str, ClauseDNA],
) -> List[ClauseAlignment]:
    """Create unmatched alignments for all blocks in document A."""
    alignments: List[ClauseAlignment] = []
    
    for block in blocks_a:
        clause_type = classifications_a.get(block["id"], "UNCERTAIN")
        if clause_type == ClauseType.ADMIN.value:
            continue
        
        dna = dna_map_a.get(block["id"])
        confidence = dna.confidence if dna else 0.0
        
        alignments.append(ClauseAlignment(
            doc_id_a=doc_id_a,
            block_id_a=block["id"],
            doc_id_b=doc_id_b,
            block_id_b=None,
            clause_type=clause_type,
            alignment_score=0.0,
            score_components={},
            confidence=confidence,
            alignment_type=AlignmentType.UNMATCHED,
            notes="No matching clause found in document B",
        ))
    
    return alignments


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_alignments(doc_id_a: str, doc_id_b: str) -> List[ClauseAlignment]:
    """Retrieve all alignments for a document pair."""
    store = AlignmentStore()
    return store.get_alignments(doc_id_a, doc_id_b)


def get_alignment(block_id_a: str) -> List[ClauseAlignment]:
    """Retrieve alignments for a specific block from document A."""
    store = AlignmentStore()
    return store.get_alignment(block_id_a)
