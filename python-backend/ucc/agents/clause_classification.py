"""Segment 3: Clause Classification Agent.

Classifies each persisted block into a single, explicit clause type
so downstream segments never compare incompatible clauses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Set, Tuple

from ..io.pdf_blocks import Block
from ..storage.classification_store import (
    BlockClassification,
    ClassificationResult,
    ClassificationStore,
    ClauseType,
    CLAUSE_TYPE_PRECEDENCE,
)
from ..storage.definitions_store import DefinitionsStore
from ..storage.layout_store import LayoutStore


# ---------------------------------------------------------------------------
# Section Path Keywords (for section-based classification)
# ---------------------------------------------------------------------------

SECTION_KEYWORDS: Dict[ClauseType, List[str]] = {
    ClauseType.DEFINITION: [
        "definition",
        "definitions",
        "glossary",
        "meaning of words",
        "interpretation",
        "what words mean",
        "key terms",
    ],
    ClauseType.EXCLUSION: [
        "exclusion",
        "exclusions",
        "what is not covered",
        "not covered",
        "we do not cover",
        "what we don't cover",
        "general exclusions",
        "specific exclusions",
    ],
    ClauseType.CONDITION: [
        "condition",
        "conditions",
        "general conditions",
        "policy conditions",
        "claims conditions",
        "your duties",
        "your obligations",
    ],
    ClauseType.LIMIT: [
        "limit",
        "limits",
        "limit of liability",
        "limits of liability",
        "sum insured",
        "maximum",
    ],
    ClauseType.SUBLIMIT: [
        "sublimit",
        "sub-limit",
        "inner limit",
        "sub limit",
    ],
    ClauseType.EXTENSION: [
        "extension",
        "extensions",
        "optional cover",
        "additional cover",
        "optional benefits",
    ],
    ClauseType.ENDORSEMENT: [
        "endorsement",
        "endorsements",
        "schedule",
        "amendment",
    ],
    ClauseType.WARRANTY: [
        "warranty",
        "warranties",
        "warranted",
    ],
    ClauseType.COVERAGE_GRANT: [
        "cover",
        "coverage",
        "insuring clause",
        "insuring agreement",
        "what is covered",
        "what we cover",
        "scope of cover",
    ],
}


# ---------------------------------------------------------------------------
# Text Patterns (for content-based classification)
# ---------------------------------------------------------------------------

@dataclass
class PatternRule:
    """A single pattern rule with score and description."""
    pattern: re.Pattern[str]
    score: float
    description: str


EXCLUSION_PATTERNS: List[PatternRule] = [
    PatternRule(
        re.compile(r"\bwe\s+will\s+not\s+(?:pay|cover|insure|indemnify)\b", re.IGNORECASE),
        0.95,
        "we will not pay/cover",
    ),
    PatternRule(
        re.compile(r"\bthis\s+policy\s+does\s+not\s+cover\b", re.IGNORECASE),
        0.95,
        "this policy does not cover",
    ),
    PatternRule(
        re.compile(r"\bno\s+cover\s+is\s+provided\s+for\b", re.IGNORECASE),
        0.90,
        "no cover is provided for",
    ),
    PatternRule(
        re.compile(r"\bwe\s+do\s+not\s+(?:pay|cover|insure)\b", re.IGNORECASE),
        0.90,
        "we do not pay/cover",
    ),
    PatternRule(
        re.compile(r"\bexclud(?:e[sd]?|ing)\b", re.IGNORECASE),
        0.75,
        "exclude/excluded/excluding",
    ),
    PatternRule(
        re.compile(r"\bnot\s+covered\b", re.IGNORECASE),
        0.70,
        "not covered",
    ),
    PatternRule(
        re.compile(r"\bexclusion\s+applies\b", re.IGNORECASE),
        0.85,
        "exclusion applies",
    ),
    PatternRule(
        re.compile(r"\bwithout\s+(?:any\s+)?cover(?:age)?\b", re.IGNORECASE),
        0.70,
        "without cover",
    ),
]

CONDITION_PATTERNS: List[PatternRule] = [
    PatternRule(
        re.compile(r"\bit\s+is\s+a\s+condition\s+(?:of\s+this\s+policy\s+)?that\b", re.IGNORECASE),
        0.95,
        "it is a condition that",
    ),
    PatternRule(
        re.compile(r"\byou\s+must\b", re.IGNORECASE),
        0.80,
        "you must",
    ),
    PatternRule(
        re.compile(r"\bsubject\s+to\s+(?:the\s+following|compliance)\b", re.IGNORECASE),
        0.75,
        "subject to the following",
    ),
    PatternRule(
        re.compile(r"\byour\s+(?:duty|duties|obligation)\b", re.IGNORECASE),
        0.80,
        "your duty/obligation",
    ),
    PatternRule(
        re.compile(r"\bfailure\s+to\s+comply\b", re.IGNORECASE),
        0.75,
        "failure to comply",
    ),
    PatternRule(
        re.compile(r"\bcondition\s+precedent\b", re.IGNORECASE),
        0.90,
        "condition precedent",
    ),
    PatternRule(
        re.compile(r"\bprovided\s+(?:that|always)\b", re.IGNORECASE),
        0.65,
        "provided that",
    ),
]

WARRANTY_PATTERNS: List[PatternRule] = [
    PatternRule(
        re.compile(r"\bwarrant(?:s|ed)?\s+that\b", re.IGNORECASE),
        0.90,
        "warrants that",
    ),
    PatternRule(
        re.compile(r"\byou\s+warrant\b", re.IGNORECASE),
        0.90,
        "you warrant",
    ),
    PatternRule(
        re.compile(r"\bthe\s+insured\s+warrants\b", re.IGNORECASE),
        0.90,
        "the insured warrants",
    ),
    PatternRule(
        re.compile(r"\bwarranty\s+(?:that|is)\b", re.IGNORECASE),
        0.85,
        "warranty that/is",
    ),
]

LIMIT_PATTERNS: List[PatternRule] = [
    PatternRule(
        re.compile(r"\blimit\s+of\s+(?:liability|indemnity)\b", re.IGNORECASE),
        0.90,
        "limit of liability",
    ),
    PatternRule(
        re.compile(r"\bmaximum\s+(?:amount|limit|we\s+will\s+pay)\b", re.IGNORECASE),
        0.85,
        "maximum amount/limit",
    ),
    PatternRule(
        re.compile(r"\bshall\s+not\s+exceed\b", re.IGNORECASE),
        0.80,
        "shall not exceed",
    ),
    PatternRule(
        re.compile(r"\bsum\s+insured\b", re.IGNORECASE),
        0.80,
        "sum insured",
    ),
    PatternRule(
        re.compile(r"\$[\d,]+(?:\.\d{2})?\s+(?:any\s+one|per)\b", re.IGNORECASE),
        0.75,
        "currency + any one/per",
    ),
    PatternRule(
        re.compile(r"\bthe\s+most\s+we\s+will\s+pay\b", re.IGNORECASE),
        0.85,
        "the most we will pay",
    ),
]

SUBLIMIT_PATTERNS: List[PatternRule] = [
    PatternRule(
        re.compile(r"\bsub[-\s]?limit\b", re.IGNORECASE),
        0.90,
        "sublimit",
    ),
    PatternRule(
        re.compile(r"\binner\s+limit\b", re.IGNORECASE),
        0.85,
        "inner limit",
    ),
    PatternRule(
        re.compile(r"\blimited\s+to\s+\$[\d,]+\b", re.IGNORECASE),
        0.70,
        "limited to $X",
    ),
]

EXTENSION_PATTERNS: List[PatternRule] = [
    PatternRule(
        re.compile(r"\bthis\s+(?:policy|cover)\s+is\s+extended\s+to\s+(?:include|cover)\b", re.IGNORECASE),
        0.90,
        "policy is extended to include",
    ),
    PatternRule(
        re.compile(r"\bcover\s+(?:is\s+)?extended\b", re.IGNORECASE),
        0.80,
        "cover extended",
    ),
    PatternRule(
        re.compile(r"\boptional\s+(?:cover|extension|benefit)\b", re.IGNORECASE),
        0.80,
        "optional cover/extension",
    ),
    PatternRule(
        re.compile(r"\badditional\s+(?:cover|benefit)\b", re.IGNORECASE),
        0.75,
        "additional cover",
    ),
]

ENDORSEMENT_PATTERNS: List[PatternRule] = [
    PatternRule(
        re.compile(r"\bendorsement\s+(?:no\.?|number)?\s*\d+\b", re.IGNORECASE),
        0.90,
        "endorsement number",
    ),
    PatternRule(
        re.compile(r"\bthis\s+endorsement\b", re.IGNORECASE),
        0.85,
        "this endorsement",
    ),
    PatternRule(
        re.compile(r"\battached\s+to\s+(?:and\s+forms?\s+part\s+of\s+)?(?:the\s+)?policy\b", re.IGNORECASE),
        0.80,
        "attached to policy",
    ),
]

COVERAGE_GRANT_PATTERNS: List[PatternRule] = [
    PatternRule(
        re.compile(r"\bwe\s+will\s+(?:pay|cover|insure|indemnify)\b", re.IGNORECASE),
        0.85,
        "we will pay/cover",
    ),
    PatternRule(
        re.compile(r"\bcover(?:age)?\s+is\s+provided\b", re.IGNORECASE),
        0.85,
        "coverage is provided",
    ),
    PatternRule(
        re.compile(r"\byou\s+are\s+(?:covered|insured)\b", re.IGNORECASE),
        0.80,
        "you are covered",
    ),
    PatternRule(
        re.compile(r"\bthis\s+policy\s+covers\b", re.IGNORECASE),
        0.85,
        "this policy covers",
    ),
    PatternRule(
        re.compile(r"\binsured\s+(?:against|for)\b", re.IGNORECASE),
        0.75,
        "insured against/for",
    ),
    PatternRule(
        re.compile(r"\bindemnify\s+(?:you|the\s+insured)\b", re.IGNORECASE),
        0.80,
        "indemnify you",
    ),
]

DEFINITION_PATTERNS: List[PatternRule] = [
    PatternRule(
        re.compile(r'^["\u201c][A-Za-z][^"\u201d]+["\u201d]\s+means\b', re.IGNORECASE),
        0.95,
        '"Term" means',
    ),
    PatternRule(
        re.compile(r"\bmeans\s+(?:any|the|a)\b", re.IGNORECASE),
        0.70,
        "means any/the/a",
    ),
    PatternRule(
        re.compile(r"\brefers?\s+to\b", re.IGNORECASE),
        0.60,
        "refers to",
    ),
    PatternRule(
        re.compile(r"\bis\s+defined\s+as\b", re.IGNORECASE),
        0.85,
        "is defined as",
    ),
]


# All patterns grouped by clause type
ALL_PATTERNS: Dict[ClauseType, List[PatternRule]] = {
    ClauseType.EXCLUSION: EXCLUSION_PATTERNS,
    ClauseType.CONDITION: CONDITION_PATTERNS,
    ClauseType.WARRANTY: WARRANTY_PATTERNS,
    ClauseType.LIMIT: LIMIT_PATTERNS,
    ClauseType.SUBLIMIT: SUBLIMIT_PATTERNS,
    ClauseType.EXTENSION: EXTENSION_PATTERNS,
    ClauseType.ENDORSEMENT: ENDORSEMENT_PATTERNS,
    ClauseType.COVERAGE_GRANT: COVERAGE_GRANT_PATTERNS,
    ClauseType.DEFINITION: DEFINITION_PATTERNS,
}


# ---------------------------------------------------------------------------
# Classification Logic
# ---------------------------------------------------------------------------

@dataclass
class _SignalMatch:
    """A matched signal with score and description."""
    clause_type: ClauseType
    score: float
    source: str  # "section" or "pattern"
    description: str


def _check_section_keywords(section_path: List[str]) -> List[_SignalMatch]:
    """Check section path against known keywords."""
    signals: List[_SignalMatch] = []
    path_lower = " ".join(section_path).lower()
    
    for clause_type, keywords in SECTION_KEYWORDS.items():
        for keyword in keywords:
            if keyword in path_lower:
                # Higher score for more specific matches
                score = 0.85 if len(keyword.split()) > 1 else 0.75
                signals.append(_SignalMatch(
                    clause_type=clause_type,
                    score=score,
                    source="section",
                    description=f"section contains '{keyword}'",
                ))
                break  # Only one match per clause type
    
    return signals


def _check_text_patterns(text: str) -> List[_SignalMatch]:
    """Check text against all pattern rules."""
    signals: List[_SignalMatch] = []
    
    for clause_type, patterns in ALL_PATTERNS.items():
        best_match: _SignalMatch | None = None
        
        for rule in patterns:
            if rule.pattern.search(text):
                match = _SignalMatch(
                    clause_type=clause_type,
                    score=rule.score,
                    source="pattern",
                    description=rule.description,
                )
                if best_match is None or match.score > best_match.score:
                    best_match = match
        
        if best_match:
            signals.append(best_match)
    
    return signals


def _resolve_conflicts(
    signals: List[_SignalMatch],
) -> Tuple[ClauseType, float, List[Dict[str, Any]]]:
    """
    Resolve conflicts using precedence order.
    
    Returns (clause_type, confidence, signals_list).
    """
    if not signals:
        return ClauseType.UNCERTAIN, 0.4, [{"rule": "no_signals_fired"}]
    
    # Group signals by clause type
    by_type: Dict[ClauseType, List[_SignalMatch]] = {}
    for signal in signals:
        if signal.clause_type not in by_type:
            by_type[signal.clause_type] = []
        by_type[signal.clause_type].append(signal)
    
    # Calculate combined score for each type
    type_scores: Dict[ClauseType, float] = {}
    for ct, sigs in by_type.items():
        # Combine scores: max + bonus for multiple signals
        max_score = max(s.score for s in sigs)
        bonus = min(0.1 * (len(sigs) - 1), 0.1)  # Small bonus for multiple signals
        type_scores[ct] = min(max_score + bonus, 1.0)
    
    # Sort by precedence
    sorted_types = sorted(
        type_scores.keys(),
        key=lambda ct: CLAUSE_TYPE_PRECEDENCE.index(ct)
        if ct in CLAUSE_TYPE_PRECEDENCE
        else len(CLAUSE_TYPE_PRECEDENCE),
    )
    
    winner = sorted_types[0]
    confidence = type_scores[winner]
    
    # Reduce confidence if there were conflicts
    if len(sorted_types) > 1:
        # Check if there's a strong competitor
        runner_up_score = type_scores[sorted_types[1]] if len(sorted_types) > 1 else 0
        if runner_up_score > 0.6:
            confidence = confidence * 0.85  # Reduce confidence due to conflict
    
    # Build signals list for output
    signals_out = [
        {
            "type": s.clause_type.value,
            "score": s.score,
            "source": s.source,
            "description": s.description,
        }
        for s in signals
    ]
    
    if len(sorted_types) > 1:
        signals_out.append({
            "type": "conflict_resolution",
            "competing_types": [ct.value for ct in sorted_types],
            "winner_by_precedence": winner.value,
        })
    
    return winner, confidence, signals_out


def _classify_block(
    block: Block,
    defined_terms: Set[str],
) -> BlockClassification:
    """
    Classify a single block.
    
    Args:
        block: The block to classify.
        defined_terms: Set of canonical defined terms for context.
    
    Returns:
        BlockClassification with type, confidence, and signals.
    """
    signals: List[_SignalMatch] = []
    
    # Step 1: Hard filters
    if block.is_admin:
        return BlockClassification(
            doc_id="",  # Will be set by caller
            block_id=block.id,
            clause_type=ClauseType.ADMIN,
            confidence=1.0,
            signals={"rule": "is_admin_flag", "hard_filter": True},
        )
    
    # Check if in definition section (hard filter)
    section_lower = " ".join(block.section_path).lower()
    definition_section_keywords = ["definition", "glossary", "meaning of words"]
    is_definition_section = any(kw in section_lower for kw in definition_section_keywords)
    
    # Additional check: does text look like a definition?
    definition_pattern = re.compile(
        r'^["\u201c]?[A-Z][A-Za-z\s\-/&]+["\u201d]?\s+(?:means|refers\s+to|is\s+defined)',
        re.IGNORECASE,
    )
    looks_like_definition = bool(definition_pattern.match(block.text.strip()))
    
    if is_definition_section and looks_like_definition:
        return BlockClassification(
            doc_id="",
            block_id=block.id,
            clause_type=ClauseType.DEFINITION,
            confidence=0.95,
            signals={
                "rule": "definition_section_and_pattern",
                "hard_filter": True,
                "section_path": block.section_path,
            },
        )
    
    # Step 2: Deterministic rule engine
    section_signals = _check_section_keywords(block.section_path)
    signals.extend(section_signals)
    
    pattern_signals = _check_text_patterns(block.text)
    signals.extend(pattern_signals)
    
    # Step 3 & 4: Conflict resolution and fallback
    clause_type, confidence, signals_out = _resolve_conflicts(signals)
    
    return BlockClassification(
        doc_id="",
        block_id=block.id,
        clause_type=clause_type,
        confidence=confidence,
        signals={"matched_signals": signals_out},
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_clause_classification(doc_id: str) -> ClassificationResult:
    """
    Run the Clause Classification Agent on a previously processed document.
    
    Args:
        doc_id: Document ID from Segment 1.
    
    Returns:
        ClassificationResult containing all block classifications.
    
    Raises:
        ValueError: If no blocks found for doc_id.
    """
    # Load blocks from Segment 1
    layout_store = LayoutStore()
    blocks = layout_store.get_blocks(doc_id)
    
    if not blocks:
        raise ValueError(f"No blocks found for doc_id: {doc_id}")
    
    # Load defined terms from Segment 2 (optional boost)
    definitions_store = DefinitionsStore()
    definitions = definitions_store.get_definitions(doc_id)
    defined_terms = {d.term_canonical for d in definitions}
    
    # Classify each block
    classifications: List[BlockClassification] = []
    stats: Dict[str, int] = {ct.value: 0 for ct in ClauseType}
    
    for block in blocks:
        clf = _classify_block(block, defined_terms)
        clf.doc_id = doc_id
        classifications.append(clf)
        stats[clf.clause_type.value] += 1
    
    # Persist results (idempotent)
    store = ClassificationStore()
    store.clear_classifications(doc_id)
    store.persist_classifications(classifications)
    
    return ClassificationResult(
        doc_id=doc_id,
        classifications=classifications,
        stats=stats,
    )


def get_blocks_by_clause_type(
    doc_id: str,
    clause_type: ClauseType,
) -> List[BlockClassification]:
    """Retrieve all blocks of a specific clause type."""
    store = ClassificationStore()
    return store.get_blocks_by_clause_type(doc_id, clause_type)


def get_classification(doc_id: str, block_id: str) -> BlockClassification | None:
    """Retrieve classification for a specific block."""
    store = ClassificationStore()
    return store.get_classification(doc_id, block_id)


def get_all_classifications(doc_id: str) -> List[BlockClassification]:
    """Retrieve all classifications for a document."""
    store = ClassificationStore()
    return store.get_all_classifications(doc_id)
