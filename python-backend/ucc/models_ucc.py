"""Data models for the Universal Clause Comparer pipeline."""

from __future__ import annotations

from typing import Dict, List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

ClauseType = Literal[
    "insuring_agreement",
    "exclusion",
    "condition",
    "definition",
    "schedule_item",
    "endorsement",
    "misc",
]


class Clause(BaseModel):
    """Represents a normalised clause extracted from a policy document."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    section_path: str
    title: Optional[str]
    type: ClauseType
    text: str
    page_start: Optional[int]
    page_end: Optional[int]
    numeric: Dict[str, float] = Field(default_factory=dict)
    confidence: float = 1.0
    hash: str


class ClauseMatch(BaseModel):
    """Represents the comparison outcome for a pair of clauses."""

    a_id: Optional[str]
    b_id: Optional[str]
    similarity: Optional[float]
    status: Literal["added", "removed", "modified", "unchanged"]
    token_diff: Optional[Dict[str, List[str]]] = None
    numeric_delta: Optional[Dict[str, Dict[str, float]]] = None
    materiality_score: float = 0.0
    strictness_delta: int = 0
    review_required: bool = False
    evidence: Dict[str, Dict[str, Optional[int]]] = Field(default_factory=dict)
    a_text: Optional[str] = None
    b_text: Optional[str] = None
    a_title: Optional[str] = None
    b_title: Optional[str] = None


class UCCComparisonResult(BaseModel):
    """Top level response model returned by the comparer."""

    summary: Dict[str, object]
    matches: List[ClauseMatch]
    unmapped_a: List[str]
    unmapped_b: List[str]
    warnings: List[str]
    timings_ms: Dict[str, float]
