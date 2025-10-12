"""Materiality and wording strictness heuristics."""

from __future__ import annotations

from typing import Dict, Iterable

from .models_ucc import Clause, ClauseMatch

BASE_WEIGHTS: Dict[str, float] = {
    "exclusion": 1.0,
    "condition": 0.9,
    "insuring_agreement": 0.8,
    "definition": 0.6,
    "endorsement": 0.8,
    "schedule_item": 0.85,
    "misc": 0.3,
}

SOFTENING_PAIRS = {
    ("shall", "may"): -1,
    ("must", "should"): -1,
    ("directly or indirectly", "directly"): -1,
    ("warranted", "requested"): -1,
    ("will", "may"): -1,
    ("is excluded", "may be excluded"): -1,
}

CARVEOUT_PHRASES = ["sudden and accidental", "except as otherwise provided"]


def base_materiality(clause: Clause) -> float:
    """Return the baseline materiality weight for a clause."""

    return BASE_WEIGHTS.get(clause.type, 0.3)


def evaluate_strictness(tokens_removed: Iterable[str], tokens_added: Iterable[str]) -> int:
    """Estimate strictness delta from removed/added tokens."""

    removed_text = " ".join(tokens_removed).lower()
    added_text = " ".join(tokens_added).lower()
    delta = 0
    for (hard, soft), score in SOFTENING_PAIRS.items():
        if hard in removed_text and soft in added_text:
            delta += score
        elif soft in removed_text and hard in added_text:
            delta -= score
    return delta


def _score_carveouts(removed_text: str, added_text: str) -> float:
    score = 0.0
    for phrase in CARVEOUT_PHRASES:
        if phrase in removed_text and phrase not in added_text:
            score += 0.1
    if "directly or indirectly" in removed_text and "directly" in added_text:
        score += 0.1
    return score


def _score_numeric(match: ClauseMatch) -> float:
    if not match.numeric_delta:
        return 0.0
    score = 0.0
    for key, delta in match.numeric_delta.items():
        pct = delta.get("pct")
        if pct is None:
            continue
        if key in {"limit", "sum_insured", "coverage_limit"} and pct < -0.25:
            score += 0.15
        if key in {"deductible", "excess"} and pct > 0.25:
            score += 0.15
    return score


def apply_materiality(match: ClauseMatch, clause_a: Clause | None, clause_b: Clause | None) -> ClauseMatch:
    """Populate materiality fields for a match record."""

    reference_clause = clause_b or clause_a
    if reference_clause is None:
        return match

    score = base_materiality(reference_clause)

    removed_text = " ".join((match.token_diff or {}).get("removed", [])).lower()
    added_text = " ".join((match.token_diff or {}).get("added", [])).lower()

    score += _score_carveouts(removed_text, added_text)
    score += _score_numeric(match)

    if match.status == "added" and clause_b and clause_b.type == "exclusion":
        score += 0.15
    if match.status == "removed" and clause_a and clause_a.type == "exclusion":
        score += 0.1

    match.materiality_score = max(0.0, min(1.0, score))
    return match
