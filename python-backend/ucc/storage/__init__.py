"""Persistence helpers for pipeline agents."""

from .layout_store import LayoutStore, PersistedDocument
from .definitions_store import (
    BlockExpansion,
    Definition,
    DefinitionsResult,
    DefinitionsStore,
    DefinitionType,
    TermMention,
)
from .classification_store import (
    BlockClassification,
    ClassificationResult,
    ClassificationStore,
    ClauseType,
    CLAUSE_TYPE_PRECEDENCE,
)
from .dna_store import (
    ClauseDNA,
    ClauseDNAResult,
    DNAStore,
    Polarity,
    Strictness,
)
from .alignment_store import (
    AlignmentResult,
    AlignmentStore,
    AlignmentType,
    ClauseAlignment,
)
from .delta_store import (
    ClauseDelta,
    DeltaDirection,
    DeltaResult,
    DeltaStore,
    DeltaType,
)

__all__ = [
    # Layout (Segment 1)
    "LayoutStore",
    "PersistedDocument",
    # Definitions (Segment 2)
    "BlockExpansion",
    "Definition",
    "DefinitionsResult",
    "DefinitionsStore",
    "DefinitionType",
    "TermMention",
    # Classification (Segment 3)
    "BlockClassification",
    "ClassificationResult",
    "ClassificationStore",
    "ClauseType",
    "CLAUSE_TYPE_PRECEDENCE",
    # DNA (Segment 4)
    "ClauseDNA",
    "ClauseDNAResult",
    "DNAStore",
    "Polarity",
    "Strictness",
    # Alignment (Segment 5)
    "AlignmentResult",
    "AlignmentStore",
    "AlignmentType",
    "ClauseAlignment",
    # Delta (Segment 6)
    "ClauseDelta",
    "DeltaDirection",
    "DeltaResult",
    "DeltaStore",
    "DeltaType",
]
