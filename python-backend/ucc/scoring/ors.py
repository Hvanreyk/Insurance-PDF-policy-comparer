"""Operational relevance scoring."""

from __future__ import annotations

from ..config_loader import get_threshold


def compute_ors(
    pos_sim: float,
    neg_sim: float,
    cue_count: int,
    section_admin: bool,
    has_concepts: bool,
) -> float:
    """Compute the operational relevance score (ORS).

    The formula is deterministic and derived from heuristics:
    - positive similarity adds support once above the configured minimum
    - negative similarity penalises above the configured maximum
    - clause cues and ontology matches provide bounded boosts
    - admin sections reduce the score unless strong cues exist
    """

    pos_floor = get_threshold("pos_sim_min", 0.45)
    neg_ceiling = get_threshold("neg_sim_max", 0.35)

    pos_term = max(0.0, pos_sim - pos_floor)
    neg_term = max(0.0, neg_sim - neg_ceiling)
    cue_boost = min(0.25, 0.08 * cue_count)
    concept_boost = 0.1 if has_concepts else 0.0
    admin_penalty = 0.15 if section_admin else 0.0

    raw = 0.45 + pos_term * 0.9 - neg_term * 0.8 + cue_boost + concept_boost - admin_penalty
    return max(0.0, min(1.0, raw))
