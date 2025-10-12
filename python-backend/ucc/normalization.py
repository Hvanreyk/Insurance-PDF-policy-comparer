"""Utilities for normalising raw policy text blocks into Clause models."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Iterable, List, Optional

from .models_ucc import Clause, ClauseType


@dataclass
class RawClauseBlock:
    """Intermediate representation produced by the parser."""

    text: str
    section_path: str
    title: Optional[str]
    page_start: Optional[int]
    page_end: Optional[int]
    confidence: float = 1.0


TYPE_KEYWORDS = {
    "exclusion": [r"we will not", r"is excluded", r"exclusion"],
    "condition": [r"condition", r"provided that", r"subject to"],
    "definition": [r"means", r"refers to"],
    "schedule_item": [r"limit", r"deductible", r"sum insured"],
    "endorsement": [r"endorsement", r"attached to"],
    "insuring_agreement": [r"we will pay", r"coverage"],
}


def classify_block(block: RawClauseBlock) -> ClauseType:
    """Classify a raw block into a clause type using heuristics."""

    lowered = block.text.lower()
    for clause_type, patterns in TYPE_KEYWORDS.items():
        for pattern in patterns:
            if re.search(pattern, lowered):
                return clause_type  # type: ignore[return-value]
    return "misc"


def canonicalise_text(text: str) -> str:
    """Normalise whitespace and trivial formatting artefacts."""

    text = re.sub(r"\s+", " ", text.strip())
    return text


def compute_hash(text: str, section_path: str) -> str:
    """Compute a stable hash for the clause content."""

    normalised = canonicalise_text(text)
    return hashlib.sha1(f"{section_path}::{normalised}".encode("utf-8")).hexdigest()


def normalise_blocks(blocks: Iterable[RawClauseBlock]) -> List[Clause]:
    """Convert parsed blocks into Clause models."""

    clauses: List[Clause] = []
    for block in blocks:
        text = canonicalise_text(block.text)
        clause_type = classify_block(block)
        clause_hash = compute_hash(text, block.section_path)
        clause = Clause(
            section_path=block.section_path,
            title=block.title,
            type=clause_type,
            text=text,
            page_start=block.page_start,
            page_end=block.page_end,
            confidence=block.confidence,
            hash=clause_hash,
        )
        clauses.append(clause)
    return clauses
