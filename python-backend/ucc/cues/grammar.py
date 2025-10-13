"""Regex cues for clause typing."""

from __future__ import annotations

from typing import Dict, Set

try:  # pragma: no cover - optional dependency
    import regex as re
except ModuleNotFoundError:  # pragma: no cover - test environment fallback
    import re  # type: ignore


CLAUSE_PATTERNS: Dict[str, re.Pattern[str]] = {
    "DEFINITION": re.compile(r"\bmeans\b|\brefers to\b", re.IGNORECASE),
    "EXCLUSION": re.compile(r"\bwill not cover\b|\bexclud(?:e|es|ed)\b", re.IGNORECASE),
    "LIMIT": re.compile(r"\blimit(?: of liability)?\b|\bshall not exceed\b", re.IGNORECASE),
    "CONDITION": re.compile(r"\bit is a condition\b|\bmust\b|\bshall\b", re.IGNORECASE),
    "GRANT": re.compile(r"\bwe will\b|\bindemnify\b|\binsure\b", re.IGNORECASE),
    "ENDORSEMENT": re.compile(r"\bendorsement\b|\bextension\b", re.IGNORECASE),
}

LIMIT_CLAMP_PATTERN = re.compile(r"\blimit\b|\bexcess\b|\bdeductible\b", re.IGNORECASE)


def detect_cues(text: str) -> Set[str]:
    matches: Set[str] = set()
    for label, pattern in CLAUSE_PATTERNS.items():
        if pattern.search(text):
            matches.add(label)
    return matches


def within_operational_length(text: str) -> bool:
    word_count = len(re.findall(r"\b\w+\b", text))
    if word_count == 0:
        return False
    if LIMIT_CLAMP_PATTERN.search(text):
        return word_count <= 1500
    return 10 <= word_count <= 1500
