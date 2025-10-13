"""Facet extraction and comparison for clause matches."""

from __future__ import annotations

from typing import Dict, List, Sequence, Set

try:  # pragma: no cover - optional dependency
    import regex as re
except ModuleNotFoundError:  # pragma: no cover - test environment fallback
    import re  # type: ignore

FACET_PATTERNS: Dict[str, re.Pattern[str]] = {
    "limit": re.compile(r"limit[^.]+", re.IGNORECASE),
    "deductible": re.compile(r"(?:deductible|excess)[^.]+", re.IGNORECASE),
    "territory": re.compile(r"(?:territor|jurisdiction)[^.]+", re.IGNORECASE),
    "notice": re.compile(r"(?:notify|notice)[^.]+", re.IGNORECASE),
    "perils": re.compile(r"(?:flood|storm|fire|cyber|pollution|terror)[^.]+", re.IGNORECASE),
    "endorsement": re.compile(r"endorsement[^.]+", re.IGNORECASE),
    "condition": re.compile(r"condition[^.]+", re.IGNORECASE),
    "exclusion": re.compile(r"does not cover[^.]+|exclud[^.]+", re.IGNORECASE),
}


def extract_facets(text: str, concepts: Sequence[str] | None = None) -> Dict[str, Set[str]]:
    facets: Dict[str, Set[str]] = {}
    for name, pattern in FACET_PATTERNS.items():
        matches = {match.group(0).strip().lower() for match in pattern.finditer(text)}
        if matches:
            if name == "perils":
                expanded: Set[str] = set()
                for match in matches:
                    parts = re.split(r"\b(?:and|,|/|;|only)\b", match)
                    for part in parts:
                        cleaned = part.strip()
                        if cleaned:
                            expanded.add(cleaned)
                if expanded:
                    matches = expanded
            facets[name] = matches
    if concepts:
        facets.setdefault("concepts", set()).update(concept.lower() for concept in concepts)
    return facets


def diff_facets(facets_a: Dict[str, Set[str]], facets_b: Dict[str, Set[str]]) -> Dict[str, List[str] | Dict[str, List[str]]]:
    broader: List[str] = []
    narrower: List[str] = []
    ambiguous: List[str] = []
    changed: Dict[str, List[str]] = {}

    all_keys = sorted(set(facets_a) | set(facets_b))
    for key in all_keys:
        values_a = facets_a.get(key, set())
        values_b = facets_b.get(key, set())
        if values_a == values_b:
            continue
        changed[key] = [sorted(values_a), sorted(values_b)]  # type: ignore[list-item]
        if values_a and not values_b:
            broader.append(f"{key}: A broader - includes {', '.join(sorted(values_a))} while B omits them")
        elif values_b and not values_a:
            narrower.append(f"{key}: A narrower - omits {', '.join(sorted(values_b))} retained by B")
        elif values_a.issuperset(values_b):
            broader.append(
                f"{key}: A broader - adds {', '.join(sorted(values_a - values_b))} alongside shared terms"
            )
        elif values_b.issuperset(values_a):
            narrower.append(
                f"{key}: A narrower - missing {', '.join(sorted(values_b - values_a))} that B includes"
            )
        else:
            ambiguous.append(
                f"{key}: A references {', '.join(sorted(values_a))}; B references {', '.join(sorted(values_b))}"
            )

    return {
        "broader": broader,
        "narrower": narrower,
        "ambiguous": ambiguous,
        "changed_facets": {k: v for k, v in changed.items()},
    }
