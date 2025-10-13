"""Ontology loading and concept linking."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, List

import yaml

try:  # pragma: no cover - optional dependency
    from rapidfuzz import fuzz
except ModuleNotFoundError:  # pragma: no cover - test environment fallback
    from difflib import SequenceMatcher

    class _FuzzModule:  # minimal shim
        @staticmethod
        def partial_ratio(a: str, b: str) -> float:
            return SequenceMatcher(None, a, b).ratio() * 100

    fuzz = _FuzzModule()

_SEEDS_DIR = Path(__file__).resolve().parent.parent / "seeds"


@dataclass
class Concept:
    name: str
    synonyms: List[str]
    include_terms: List[str]
    exclude_terms: List[str]

    def matches(self, text: str) -> bool:
        lowered = text.lower()
        for term in self.exclude_terms:
            if term and term.lower() in lowered:
                return False
        for include in self.include_terms:
            if include.lower() not in lowered:
                return False
        for synonym in self.synonyms:
            if fuzz.partial_ratio(synonym.lower(), lowered) >= 80:
                return True
        return False


@lru_cache(maxsize=1)
def load_ontology() -> Dict[str, Concept]:
    path = _SEEDS_DIR / "ontology_universal.yml"
    if not path.exists():  # pragma: no cover - defensive
        raise FileNotFoundError("Ontology seed file missing")
    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    ontology: Dict[str, Concept] = {}
    for name, data in raw.items():
        ontology[name] = Concept(
            name=name,
            synonyms=list(data.get("synonyms", [])),
            include_terms=list(data.get("include_terms", [])),
            exclude_terms=list(data.get("exclude_terms", [])),
        )
    return ontology


def link_concepts(text: str) -> List[str]:
    ontology = load_ontology()
    matches: List[str] = []
    for concept_id, concept in ontology.items():
        if concept.matches(text):
            matches.append(concept_id)
    return matches
