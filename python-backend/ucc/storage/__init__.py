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
]
