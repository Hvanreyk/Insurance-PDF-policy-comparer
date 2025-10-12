"""Generate factual summaries for comparison results."""

from __future__ import annotations

from typing import List, Optional

from .models_ucc import ClauseMatch


def _format_pages(evidence: Optional[dict]) -> str:
    if not evidence:
        return "unknown page"
    page_start = evidence.get("page_start")
    page_end = evidence.get("page_end")
    if page_start is None and page_end is None:
        return "unknown page"
    if page_start is None:
        return f"page {page_end}"
    if page_end is None or page_end == page_start:
        return f"page {page_start}"
    return f"pages {page_start}-{page_end}"


def summarise_matches(matches: List[ClauseMatch]) -> List[str]:
    """Return a list of neutral bullet summaries."""

    bullets: List[str] = []
    prioritized = [
        match
        for match in matches
        if match.status in {"added", "removed", "modified"}
    ]
    prioritized.sort(key=lambda m: m.materiality_score, reverse=True)

    for match in prioritized[:5]:
        clause_ref = match.b_id or match.a_id or "unknown"
        evidence = match.evidence.get("b") or match.evidence.get("a")
        page_text = _format_pages(evidence)
        strictness_note = ""
        if match.strictness_delta < 0:
            strictness_note = " (softened wording)"
        elif match.strictness_delta > 0:
            strictness_note = " (tightened wording)"
        bullets.append(
            f"{match.status.title()} clause {clause_ref} on {page_text}; materiality {match.materiality_score:.2f}{strictness_note}"
        )

    if not bullets:
        bullets.append("No material clause changes detected")
    return bullets
