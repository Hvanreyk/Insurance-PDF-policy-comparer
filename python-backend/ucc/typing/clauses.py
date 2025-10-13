"""Rule-based clause typing."""

from __future__ import annotations

from enum import Enum
from typing import Set

from ..cues.grammar import CLAUSE_PATTERNS, detect_cues


class ClauseType(str, Enum):
    DEFINITION = "DEFINITION"
    EXCLUSION = "EXCLUSION"
    LIMIT = "LIMIT"
    CONDITION = "CONDITION"
    GRANT = "GRANT"
    ENDORSEMENT = "ENDORSEMENT"
    UNKNOWN = "UNKNOWN"


_PRIORITY = [
    ClauseType.DEFINITION,
    ClauseType.EXCLUSION,
    ClauseType.LIMIT,
    ClauseType.CONDITION,
    ClauseType.GRANT,
    ClauseType.ENDORSEMENT,
]


def classify_clause(text: str, cues: Set[str] | None = None) -> ClauseType:
    cues = cues or detect_cues(text)
    for clause_type in _PRIORITY:
        if clause_type.value in cues:
            return clause_type
    if CLAUSE_PATTERNS[ClauseType.GRANT.value].search(text):
        return ClauseType.GRANT
    return ClauseType.UNKNOWN
