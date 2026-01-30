"""Segment 4: Clause DNA Agent (Legal Feature Extraction).

Converts each classified clause into a structured, explainable legal fingerprint
so downstream segments can compare how clauses operate, not just what words they contain.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Set, Tuple

from ..io.pdf_blocks import Block
from ..ontology.schema import load_ontology
from ..storage.classification_store import BlockClassification, ClassificationStore, ClauseType
from ..storage.definitions_store import DefinitionsStore
from ..storage.dna_store import (
    ClauseDNA,
    ClauseDNAResult,
    DNAStore,
    Polarity,
    Strictness,
)
from ..storage.layout_store import LayoutStore


# ---------------------------------------------------------------------------
# Pattern Definitions
# ---------------------------------------------------------------------------

# Scope connectors (widening/narrowing language)
SCOPE_CONNECTOR_PATTERNS: List[Tuple[re.Pattern[str], str]] = [
    (re.compile(r"\barising\s+(?:out\s+of|from)\b", re.IGNORECASE), "arising from"),
    (re.compile(r"\bin\s+connection\s+with\b", re.IGNORECASE), "in connection with"),
    (re.compile(r"\bdirectly\s+or\s+indirectly\b", re.IGNORECASE), "directly or indirectly"),
    (re.compile(r"\bcaused\s+by\s+or\s+contributed\s+to\b", re.IGNORECASE), "caused by or contributed to"),
    (re.compile(r"\bcaused\s+by\s+or\s+resulting\s+from\b", re.IGNORECASE), "caused by or resulting from"),
    (re.compile(r"\battributable\s+to\b", re.IGNORECASE), "attributable to"),
    (re.compile(r"\brelated\s+to\b", re.IGNORECASE), "related to"),
    (re.compile(r"\bwholly\s+or\s+partly\b", re.IGNORECASE), "wholly or partly"),
    (re.compile(r"\bdirectly\s+caused\s+by\b", re.IGNORECASE), "directly caused by"),
    (re.compile(r"\bproximate(?:ly)?\s+caused?\b", re.IGNORECASE), "proximately caused"),
    (re.compile(r"\bany\s+way\s+connected\b", re.IGNORECASE), "any way connected"),
    (re.compile(r"\bhowsoever\s+(?:caused|arising)\b", re.IGNORECASE), "howsoever caused/arising"),
]

# Carve-out trigger words
CARVE_OUT_TRIGGERS = [
    (re.compile(r"\bexcept\s+(?:for\s+|where\s+|when\s+|that\s+|to\s+the\s+extent\s+)?", re.IGNORECASE), "except"),
    (re.compile(r"\bunless\b", re.IGNORECASE), "unless"),
    (re.compile(r"\bprovided\s+(?:that|always)\b", re.IGNORECASE), "provided that"),
    (re.compile(r"\bsave\s+for\b", re.IGNORECASE), "save for"),
    (re.compile(r"\bother\s+than\b", re.IGNORECASE), "other than"),
    (re.compile(r"\bexcluding\b", re.IGNORECASE), "excluding"),
    (re.compile(r"\bnot\s+including\b", re.IGNORECASE), "not including"),
]

# Strictness patterns
ABSOLUTE_PATTERNS = [
    re.compile(r"\bwill\s+not\s+(?:cover|pay|insure|indemnify)\b", re.IGNORECASE),
    re.compile(r"\bno\s+cover\s+is\s+provided\b", re.IGNORECASE),
    re.compile(r"\bshall\s+not\b", re.IGNORECASE),
    re.compile(r"\bis\s+excluded\b", re.IGNORECASE),
    re.compile(r"\bwe\s+do\s+not\s+(?:cover|pay)\b", re.IGNORECASE),
    re.compile(r"\babsolutely\s+excluded\b", re.IGNORECASE),
    re.compile(r"\bunder\s+no\s+circumstances\b", re.IGNORECASE),
    re.compile(r"\bin\s+no\s+event\b", re.IGNORECASE),
]

CONDITIONAL_PATTERNS = [
    re.compile(r"\bsubject\s+to\b", re.IGNORECASE),
    re.compile(r"\bprovided\s+(?:that|always)\b", re.IGNORECASE),
    re.compile(r"\bunless\b", re.IGNORECASE),
    re.compile(r"\bif\s+(?:and\s+only\s+if|you)\b", re.IGNORECASE),
    re.compile(r"\bwhere\b", re.IGNORECASE),
    re.compile(r"\bwhen\b", re.IGNORECASE),
    re.compile(r"\bon\s+condition\s+that\b", re.IGNORECASE),
]

DISCRETIONARY_PATTERNS = [
    re.compile(r"\bmay\b", re.IGNORECASE),
    re.compile(r"\bat\s+(?:our|the\s+insurer(?:'s)?)\s+(?:sole\s+)?discretion\b", re.IGNORECASE),
    re.compile(r"\bin\s+(?:our|the\s+insurer(?:'s)?)\s+(?:sole\s+)?(?:and\s+absolute\s+)?discretion\b", re.IGNORECASE),
    re.compile(r"\breasonably\s+(?:determine|decide)\b", re.IGNORECASE),
    re.compile(r"\bat\s+(?:our|the\s+insurer(?:'s)?)\s+option\b", re.IGNORECASE),
]

# Temporal constraint patterns
TEMPORAL_PATTERNS: List[Tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bduring\s+the\s+period\s+of\s+insurance\b", re.IGNORECASE), "during the period of insurance"),
    (re.compile(r"\bprior\s+to\s+(?:the\s+)?inception\b", re.IGNORECASE), "prior to inception"),
    (re.compile(r"\bbefore\s+the\s+(?:policy\s+)?commencement\b", re.IGNORECASE), "before commencement"),
    (re.compile(r"\bafter\s+(?:the\s+)?expiry\b", re.IGNORECASE), "after expiry"),
    (re.compile(r"\bwithin\s+(\d+)\s+(days?|months?|years?)\b", re.IGNORECASE), "within {0} {1}"),
    (re.compile(r"\bat\s+all\s+times\b", re.IGNORECASE), "at all times"),
    (re.compile(r"\bthroughout\s+the\s+(?:policy\s+)?period\b", re.IGNORECASE), "throughout the period"),
    (re.compile(r"\bas\s+soon\s+as\s+(?:reasonably\s+)?practicable\b", re.IGNORECASE), "as soon as practicable"),
    (re.compile(r"\bimmediately\b", re.IGNORECASE), "immediately"),
    (re.compile(r"\bpromptly\b", re.IGNORECASE), "promptly"),
    (re.compile(r"\bfrom\s+the\s+date\s+of\b", re.IGNORECASE), "from the date of"),
]

# Burden shift patterns
BURDEN_SHIFT_PATTERNS = [
    re.compile(r"\byou\s+must\b", re.IGNORECASE),
    re.compile(r"\bthe\s+insured\s+(?:must|shall)\b", re.IGNORECASE),
    re.compile(r"\byour\s+(?:duty|duties|obligation)\b", re.IGNORECASE),
    re.compile(r"\bit\s+is\s+(?:a\s+)?condition\s+(?:of\s+this\s+policy\s+)?that\s+you\b", re.IGNORECASE),
    re.compile(r"\byou\s+(?:shall|are\s+required\s+to)\b", re.IGNORECASE),
    re.compile(r"\bnotify\s+us\b", re.IGNORECASE),
    re.compile(r"\bgive\s+(?:us\s+)?(?:written\s+)?notice\b", re.IGNORECASE),
    re.compile(r"\bprovide\s+(?:us\s+with\s+)?(?:all\s+)?(?:information|documents|evidence)\b", re.IGNORECASE),
    re.compile(r"\bcooperate\s+with\s+(?:us|the\s+insurer)\b", re.IGNORECASE),
    re.compile(r"\bproof\s+of\s+loss\b", re.IGNORECASE),
    re.compile(r"\bthe\s+onus\s+(?:is\s+)?on\s+(?:you|the\s+insured)\b", re.IGNORECASE),
]

# Number extraction patterns
NUMBER_PATTERNS: Dict[str, re.Pattern[str]] = {
    "currency": re.compile(
        r"(?:(?:AUD|USD|GBP|EUR|\$|£|€)\s*)?([\d,]+(?:\.\d{2})?)\s*(?:million|m|thousand|k)?",
        re.IGNORECASE
    ),
    "percentage": re.compile(r"(\d+(?:\.\d+)?)\s*%", re.IGNORECASE),
    "days": re.compile(r"(\d+)\s*(?:calendar\s+)?days?", re.IGNORECASE),
    "months": re.compile(r"(\d+)\s*months?", re.IGNORECASE),
    "years": re.compile(r"(\d+)\s*years?", re.IGNORECASE),
    "hours": re.compile(r"(\d+)\s*hours?", re.IGNORECASE),
}

# Specific number context patterns
LIMIT_CONTEXT = re.compile(r"\blimit\b|\bmaximum\b|\bup\s+to\b|\bnot\s+exceed\b", re.IGNORECASE)
DEDUCTIBLE_CONTEXT = re.compile(r"\bexcess\b|\bdeductible\b|\bretention\b|\bself[-\s]?insured\b", re.IGNORECASE)
SUBLIMIT_CONTEXT = re.compile(r"\bsub[-\s]?limit\b|\binner\s+limit\b", re.IGNORECASE)
WAITING_CONTEXT = re.compile(r"\bwaiting\s+period\b|\btime\s+excess\b|\bhours?\s+excess\b", re.IGNORECASE)

# Entity/Peril keywords (simplified from ontology)
PERIL_KEYWORDS: Dict[str, List[str]] = {
    "fire": ["fire", "flame", "burn", "combustion"],
    "flood": ["flood", "water damage", "inundation", "overflow"],
    "storm": ["storm", "tempest", "wind", "cyclone", "hurricane", "tornado"],
    "earthquake": ["earthquake", "seismic", "tremor"],
    "cyber": ["cyber", "data breach", "ransomware", "malware", "hack", "network security"],
    "pollution": ["pollution", "contamination", "seepage", "emission", "discharge"],
    "terrorism": ["terrorism", "terrorist", "terror act"],
    "war": ["war", "warlike", "hostile act", "civil war", "insurrection"],
    "asbestos": ["asbestos", "asbestosis"],
    "nuclear": ["nuclear", "radioactive", "radiation", "ionising"],
    "theft": ["theft", "burglary", "robbery", "stolen"],
    "fraud": ["fraud", "dishonest", "fraudulent"],
    "negligence": ["negligence", "negligent", "error", "omission"],
    "liability": ["liability", "civil liability", "legal liability"],
    "professional_indemnity": ["professional indemnity", "professional liability", "PI"],
}

PROPERTY_KEYWORDS: Dict[str, List[str]] = {
    "building": ["building", "structure", "premises", "property"],
    "contents": ["contents", "stock", "inventory", "equipment"],
    "vehicles": ["vehicle", "motor", "car", "fleet"],
    "machinery": ["machinery", "plant", "equipment"],
    "data": ["data", "electronic records", "software"],
    "documents": ["documents", "records", "papers"],
    "money": ["money", "cash", "currency", "negotiable instruments"],
}

SUBJECT_KEYWORDS: Dict[str, List[str]] = {
    "insured": ["insured", "policyholder", "you"],
    "employee": ["employee", "staff", "worker"],
    "contractor": ["contractor", "subcontractor", "consultant"],
    "third_party": ["third party", "claimant", "plaintiff"],
    "director": ["director", "officer", "D&O"],
}


# ---------------------------------------------------------------------------
# Feature Extraction Functions
# ---------------------------------------------------------------------------


def _extract_polarity(
    clause_type: ClauseType,
    text: str,
) -> Tuple[Polarity, List[str]]:
    """Determine the effect direction of a clause."""
    signals: List[str] = []
    
    # Use clause type as strong prior
    type_polarity_map = {
        ClauseType.COVERAGE_GRANT: Polarity.GRANT,
        ClauseType.EXCLUSION: Polarity.REMOVE,
        ClauseType.CONDITION: Polarity.RESTRICT,
        ClauseType.LIMIT: Polarity.RESTRICT,
        ClauseType.SUBLIMIT: Polarity.RESTRICT,
        ClauseType.WARRANTY: Polarity.RESTRICT,
        ClauseType.EXTENSION: Polarity.GRANT,
        ClauseType.ENDORSEMENT: Polarity.NEUTRAL,  # Could be either
        ClauseType.DEFINITION: Polarity.NEUTRAL,
        ClauseType.ADMIN: Polarity.NEUTRAL,
        ClauseType.UNCERTAIN: Polarity.NEUTRAL,
    }
    
    polarity = type_polarity_map.get(clause_type, Polarity.NEUTRAL)
    signals.append(f"clause_type={clause_type.value}")
    
    # Check for grant language in endorsements
    if clause_type == ClauseType.ENDORSEMENT:
        if re.search(r"\bextend(?:s|ed)?\s+(?:to\s+)?(?:include|cover)\b", text, re.IGNORECASE):
            polarity = Polarity.GRANT
            signals.append("endorsement extends coverage")
        elif re.search(r"\bexclud(?:e|es|ed)\b|\bremov(?:e|es|ed)\b", text, re.IGNORECASE):
            polarity = Polarity.REMOVE
            signals.append("endorsement removes coverage")
    
    return polarity, signals


def _extract_strictness(text: str) -> Tuple[Strictness, List[str]]:
    """Detect how absolute the clause language is."""
    signals: List[str] = []
    
    # Check absolute first (highest priority)
    for pattern in ABSOLUTE_PATTERNS:
        match = pattern.search(text)
        if match:
            signals.append(f"absolute: '{match.group()}'")
            return Strictness.ABSOLUTE, signals
    
    # Check discretionary (before conditional to catch "may" first)
    for pattern in DISCRETIONARY_PATTERNS:
        match = pattern.search(text)
        if match:
            signals.append(f"discretionary: '{match.group()}'")
            return Strictness.DISCRETIONARY, signals
    
    # Check conditional
    for pattern in CONDITIONAL_PATTERNS:
        match = pattern.search(text)
        if match:
            signals.append(f"conditional: '{match.group()}'")
            return Strictness.CONDITIONAL, signals
    
    # Default to conditional if no clear signal
    signals.append("no strict indicators found, defaulting to conditional")
    return Strictness.CONDITIONAL, signals


def _extract_scope_connectors(text: str) -> Tuple[List[str], List[str]]:
    """Extract widening/narrowing scope language."""
    connectors: List[str] = []
    signals: List[str] = []
    
    for pattern, label in SCOPE_CONNECTOR_PATTERNS:
        match = pattern.search(text)
        if match:
            connectors.append(label)
            signals.append(f"scope_connector: '{match.group()}'")
    
    return connectors, signals


def _extract_carve_outs(text: str) -> Tuple[List[str], List[str]]:
    """Extract trailing exceptions after carve-out triggers."""
    carve_outs: List[str] = []
    signals: List[str] = []
    
    for pattern, label in CARVE_OUT_TRIGGERS:
        for match in pattern.finditer(text):
            # Get text after the trigger up to sentence boundary
            start = match.end()
            remainder = text[start:]
            
            # Find sentence boundary (. or ; or end of text)
            end_match = re.search(r'[.;]|\Z', remainder)
            if end_match:
                carve_out_text = remainder[:end_match.start()].strip()
                if carve_out_text and len(carve_out_text) > 3:
                    # Truncate long carve-outs
                    if len(carve_out_text) > 200:
                        carve_out_text = carve_out_text[:200] + "..."
                    carve_outs.append(f"{label}: {carve_out_text}")
                    signals.append(f"carve_out '{label}' at pos {match.start()}")
    
    return carve_outs, signals


def _extract_entities(text: str) -> Tuple[List[str], List[str]]:
    """Extract perils, subjects, and property types."""
    entities: List[str] = []
    signals: List[str] = []
    text_lower = text.lower()
    
    # Extract perils
    for peril, keywords in PERIL_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in text_lower:
                if peril not in entities:
                    entities.append(f"peril:{peril}")
                    signals.append(f"peril '{keyword}'")
                break
    
    # Extract property types
    for prop_type, keywords in PROPERTY_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in text_lower:
                if f"property:{prop_type}" not in entities:
                    entities.append(f"property:{prop_type}")
                    signals.append(f"property '{keyword}'")
                break
    
    # Extract subjects
    for subject, keywords in SUBJECT_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in text_lower:
                if f"subject:{subject}" not in entities:
                    entities.append(f"subject:{subject}")
                    signals.append(f"subject '{keyword}'")
                break
    
    # Also use ontology for additional entities
    ontology = load_ontology()
    for concept_id, concept in ontology.items():
        if concept.matches(text):
            entity_key = f"concept:{concept_id}"
            if entity_key not in entities:
                entities.append(entity_key)
                signals.append(f"ontology_concept '{concept_id}'")
    
    return entities, signals


def _extract_numbers(text: str, clause_type: ClauseType) -> Tuple[Dict[str, Any], List[str]]:
    """Extract numeric features relevant to clause type."""
    numbers: Dict[str, Any] = {}
    signals: List[str] = []
    
    # Context patterns with their category names
    context_patterns = [
        (SUBLIMIT_CONTEXT, "sublimits"),  # More specific patterns first
        (DEDUCTIBLE_CONTEXT, "deductibles"),
        (LIMIT_CONTEXT, "limits"),
    ]
    
    # Maximum distance to associate an amount with a context keyword
    MAX_CONTEXT_DISTANCE = 80
    
    # Extract currency amounts with proximity-based context
    currency_pattern = NUMBER_PATTERNS["currency"]
    categorized: Dict[str, List[float]] = {
        "limits": [],
        "sublimits": [],
        "deductibles": [],
        "amounts": [],  # uncategorized
    }
    
    for match in currency_pattern.finditer(text):
        try:
            # Clean and convert to float
            clean_val = match.group(1).replace(",", "")
            val = float(clean_val)
        except (ValueError, AttributeError, IndexError):
            continue
        
        amount_pos = match.start()
        
        # Find the nearest context keyword and its category
        nearest_category = None
        nearest_distance = MAX_CONTEXT_DISTANCE + 1
        
        for pattern, category in context_patterns:
            for ctx_match in pattern.finditer(text):
                # Calculate distance from context keyword to amount
                # Context can appear before or after the amount
                ctx_start = ctx_match.start()
                ctx_end = ctx_match.end()
                
                if ctx_end <= amount_pos:
                    # Context is before amount
                    distance = amount_pos - ctx_end
                else:
                    # Context is after amount
                    distance = ctx_start - match.end()
                
                # Only consider contexts within the max distance
                if 0 <= distance < nearest_distance:
                    nearest_distance = distance
                    nearest_category = category
        
        # Assign to the nearest category, or "amounts" if no context found
        if nearest_category:
            categorized[nearest_category].append(val)
        else:
            categorized["amounts"].append(val)
    
    # Populate numbers dict and signals only for non-empty categories
    for category, values in categorized.items():
        if values:
            numbers[category] = values
            signals.append(f"{category}: {values}")
    
    # Extract percentages
    pct_matches = NUMBER_PATTERNS["percentage"].findall(text)
    if pct_matches:
        percentages = [float(p) for p in pct_matches]
        numbers["percentages"] = percentages
        signals.append(f"percentages: {percentages}")
    
    # Extract time periods
    for unit in ["days", "months", "years", "hours"]:
        matches = NUMBER_PATTERNS[unit].findall(text)
        if matches:
            values = [int(m) for m in matches]
            if WAITING_CONTEXT.search(text):
                numbers[f"waiting_period_{unit}"] = values
                signals.append(f"waiting_period_{unit}: {values}")
            else:
                numbers[f"time_{unit}"] = values
                signals.append(f"time_{unit}: {values}")
    
    return numbers, signals


def _extract_temporal_constraints(text: str) -> Tuple[List[str], List[str]]:
    """Extract temporal constraint phrases."""
    constraints: List[str] = []
    signals: List[str] = []
    
    for pattern, label in TEMPORAL_PATTERNS:
        match = pattern.search(text)
        if match:
            # Handle patterns with groups (like "within X days")
            if match.groups():
                constraint = label.format(*match.groups())
            else:
                constraint = label
            
            if constraint not in constraints:
                constraints.append(constraint)
                signals.append(f"temporal: '{match.group()}'")
    
    return constraints, signals


def _extract_burden_shift(text: str) -> Tuple[bool, List[str]]:
    """Detect if clause introduces insured obligations."""
    signals: List[str] = []
    
    for pattern in BURDEN_SHIFT_PATTERNS:
        match = pattern.search(text)
        if match:
            signals.append(f"burden_shift: '{match.group()}'")
            return True, signals
    
    return False, signals


def _get_definition_dependencies(
    doc_id: str,
    block_id: str,
    definitions_store: DefinitionsStore,
) -> Tuple[List[str], List[str]]:
    """Get defined terms used in this block."""
    signals: List[str] = []
    
    mentions = definitions_store.get_mentions(doc_id, block_id)
    terms = list({m.term_canonical for m in mentions})
    
    if terms:
        signals.append(f"definition_mentions: {len(mentions)}")
    
    return sorted(terms), signals


def _calculate_confidence(
    classification_confidence: float,
    signal_counts: Dict[str, int],
) -> float:
    """Calculate overall DNA confidence."""
    confidence = classification_confidence
    
    # Boost for strong signals
    if signal_counts.get("polarity", 0) > 0:
        confidence = min(confidence + 0.02, 1.0)
    if signal_counts.get("strictness", 0) > 0:
        confidence = min(confidence + 0.02, 1.0)
    if signal_counts.get("scope_connectors", 0) > 0:
        confidence = min(confidence + 0.01, 1.0)
    if signal_counts.get("entities", 0) >= 2:
        confidence = min(confidence + 0.02, 1.0)
    
    # Reduce for conflicting signals (e.g., both absolute and conditional)
    if signal_counts.get("conflicting", 0) > 0:
        confidence = confidence * 0.9
    
    return round(confidence, 3)


# ---------------------------------------------------------------------------
# Main Extraction Function
# ---------------------------------------------------------------------------


def _extract_clause_dna(
    block: Block,
    classification: BlockClassification,
    definitions_store: DefinitionsStore,
) -> ClauseDNA:
    """Extract all DNA features from a classified block."""
    
    text = block.text
    doc_id = classification.doc_id
    block_id = block.id
    clause_type = classification.clause_type
    
    raw_signals: Dict[str, List[str]] = {}
    signal_counts: Dict[str, int] = {}
    
    # 1. Polarity
    polarity, polarity_signals = _extract_polarity(clause_type, text)
    raw_signals["polarity"] = polarity_signals
    signal_counts["polarity"] = len(polarity_signals)
    
    # 2. Strictness
    strictness, strictness_signals = _extract_strictness(text)
    raw_signals["strictness"] = strictness_signals
    signal_counts["strictness"] = len(strictness_signals)
    
    # 3. Scope connectors
    scope_connectors, scope_signals = _extract_scope_connectors(text)
    raw_signals["scope_connectors"] = scope_signals
    signal_counts["scope_connectors"] = len(scope_connectors)
    
    # 4. Carve-outs
    carve_outs, carve_signals = _extract_carve_outs(text)
    raw_signals["carve_outs"] = carve_signals
    signal_counts["carve_outs"] = len(carve_outs)
    
    # 5. Entities
    entities, entity_signals = _extract_entities(text)
    raw_signals["entities"] = entity_signals
    signal_counts["entities"] = len(entities)
    
    # 6. Numbers
    numbers, number_signals = _extract_numbers(text, clause_type)
    raw_signals["numbers"] = number_signals
    signal_counts["numbers"] = len(numbers)
    
    # 7. Definition dependencies
    definition_deps, def_signals = _get_definition_dependencies(
        doc_id, block_id, definitions_store
    )
    raw_signals["definition_dependencies"] = def_signals
    signal_counts["definition_dependencies"] = len(definition_deps)
    
    # 8. Temporal constraints
    temporal_constraints, temporal_signals = _extract_temporal_constraints(text)
    raw_signals["temporal_constraints"] = temporal_signals
    signal_counts["temporal_constraints"] = len(temporal_constraints)
    
    # 9. Burden shift
    burden_shift, burden_signals = _extract_burden_shift(text)
    raw_signals["burden_shift"] = burden_signals
    signal_counts["burden_shift"] = 1 if burden_shift else 0
    
    # 10. Confidence
    confidence = _calculate_confidence(classification.confidence, signal_counts)
    
    return ClauseDNA(
        doc_id=doc_id,
        block_id=block_id,
        clause_type=clause_type,
        polarity=polarity,
        strictness=strictness,
        scope_connectors=scope_connectors,
        carve_outs=carve_outs,
        entities=entities,
        numbers=numbers,
        definition_dependencies=definition_deps,
        temporal_constraints=temporal_constraints,
        burden_shift=burden_shift,
        raw_signals=raw_signals,
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_clause_dna_agent(doc_id: str) -> ClauseDNAResult:
    """
    Run the Clause DNA Agent on a previously processed document.
    
    Args:
        doc_id: Document ID from Segment 1.
    
    Returns:
        ClauseDNAResult containing all clause DNA records.
    
    Raises:
        ValueError: If no blocks or classifications found for doc_id.
    """
    # Load blocks from Segment 1
    layout_store = LayoutStore()
    blocks = layout_store.get_blocks(doc_id)
    
    if not blocks:
        raise ValueError(f"No blocks found for doc_id: {doc_id}")
    
    # Load classifications from Segment 3
    classification_store = ClassificationStore()
    classifications = classification_store.get_all_classifications(doc_id)
    
    if not classifications:
        raise ValueError(f"No classifications found for doc_id: {doc_id}")
    
    # Build lookup maps
    blocks_by_id = {b.id: b for b in blocks}
    classifications_by_id = {c.block_id: c for c in classifications}
    
    # Load definitions store for dependency lookup
    definitions_store = DefinitionsStore()
    
    # Extract DNA for each classified block
    dna_records: List[ClauseDNA] = []
    stats: Dict[str, int] = {
        "total": 0,
        "with_scope_connectors": 0,
        "with_carve_outs": 0,
        "with_burden_shift": 0,
        "with_numbers": 0,
    }
    
    for classification in classifications:
        block = blocks_by_id.get(classification.block_id)
        if not block:
            continue
        
        dna = _extract_clause_dna(block, classification, definitions_store)
        dna_records.append(dna)
        
        # Update stats
        stats["total"] += 1
        if dna.scope_connectors:
            stats["with_scope_connectors"] += 1
        if dna.carve_outs:
            stats["with_carve_outs"] += 1
        if dna.burden_shift:
            stats["with_burden_shift"] += 1
        if dna.numbers:
            stats["with_numbers"] += 1
    
    # Persist results (idempotent)
    dna_store = DNAStore()
    dna_store.clear_dna(doc_id)
    dna_store.persist_dna(dna_records)
    
    return ClauseDNAResult(
        doc_id=doc_id,
        dna_records=dna_records,
        stats=stats,
    )


def get_clause_dna(doc_id: str, block_id: str) -> ClauseDNA | None:
    """Retrieve DNA for a specific block."""
    store = DNAStore()
    return store.get_dna(doc_id, block_id)


def get_dna_by_type(doc_id: str, clause_type: ClauseType) -> List[ClauseDNA]:
    """Retrieve all DNA records for a specific clause type."""
    store = DNAStore()
    return store.get_dna_by_type(doc_id, clause_type)


def get_all_dna(doc_id: str) -> List[ClauseDNA]:
    """Retrieve all DNA records for a document."""
    store = DNAStore()
    return store.get_all_dna(doc_id)
