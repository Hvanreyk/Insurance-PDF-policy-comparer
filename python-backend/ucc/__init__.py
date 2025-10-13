"""Universal Clause Comparer package."""

from .models_ucc import Clause, ClauseMatch, UCCComparisonResult
from .pipeline import ComparisonOptions, UCCComparer
from .service import align_policy_blocks, diff_policy_facets, preprocess_policy

__all__ = [
    "Clause",
    "ClauseMatch",
    "UCCComparisonResult",
    "ComparisonOptions",
    "UCCComparer",
    "preprocess_policy",
    "align_policy_blocks",
    "diff_policy_facets",
]
