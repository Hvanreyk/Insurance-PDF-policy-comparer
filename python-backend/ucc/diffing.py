"""Token level diffing utilities for clause comparison."""

from __future__ import annotations

import difflib
from typing import Dict, List

from ucc.models_ucc import Clause


def tokenise(text: str) -> List[str]:
    """Split text into comparable tokens."""

    return text.replace("\n", " ").split()


def diff_tokens(a: Clause, b: Clause) -> Dict[str, List[str]]:
    """Return added/removed tokens between two clauses."""

    seq_a = tokenise(a.text)
    seq_b = tokenise(b.text)
    diff = difflib.ndiff(seq_a, seq_b)
    added: List[str] = []
    removed: List[str] = []
    for token in diff:
        if token.startswith("+ "):
            added.append(token[2:])
        elif token.startswith("- "):
            removed.append(token[2:])
    return {"added": added, "removed": removed}


def similarity_ratio(a: Clause, b: Clause) -> float:
    """Compute a similarity ratio for two clauses."""

    matcher = difflib.SequenceMatcher(None, a.text, b.text)
    return matcher.ratio()


def classify_status(similarity: float, token_diff: Dict[str, List[str]]) -> str:
    """Classify the change status based on similarity and token diff."""

    added = len(token_diff.get("added", []))
    removed = len(token_diff.get("removed", []))
    if similarity >= 0.95 and added == 0 and removed == 0:
        return "unchanged"
    if similarity >= 0.85:
        return "modified"
    return "modified"


def compute_numeric_delta(a: Clause, b: Clause) -> Dict[str, Dict[str, float]]:
    """Compute percentage change for overlapping numeric fields."""

    delta: Dict[str, Dict[str, float]] = {}
    for key, value_a in a.numeric.items():
        if key in b.numeric:
            value_b = b.numeric[key]
            if value_a is None or value_b is None:
                continue
            if value_a == 0:
                pct = 0.0
            else:
                pct = (value_b - value_a) / value_a
            delta[key] = {"a": float(value_a), "b": float(value_b), "pct": float(pct)}
    return delta


def has_token_changes(token_diff: Dict[str, List[str]]) -> bool:
    """Return True if any token level changes were detected."""

    return bool(token_diff.get("added")) or bool(token_diff.get("removed"))
