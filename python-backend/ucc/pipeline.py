"""End-to-end comparison pipeline for the Universal Clause Comparer."""

from __future__ import annotations

import gc
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from typing import TYPE_CHECKING

from ucc.alignment import AlignmentOptions, align_clauses
from ucc.diffing import classify_status, compute_numeric_delta, diff_tokens
from ucc.materiality import apply_materiality, evaluate_strictness
from ucc.models_ucc import Clause, ClauseMatch, UCCComparisonResult
from ucc.summarizer import summarise_matches

if TYPE_CHECKING:  # pragma: no cover - typing helper
    from pdf_parser import parse_document_to_clauses


@dataclass
class ComparisonOptions:
    """High-level options for the comparer."""

    embedder: str = "auto"
    similarity_threshold: float = 0.72
    return_token_diffs: bool = True
    max_candidates_per_clause: int = 2


class ClauseLookup:
    """Helper structure for quick clause access."""

    def __init__(self, clauses: Sequence[Clause]):
        self.by_id: Dict[str, Clause] = {clause.id: clause for clause in clauses}

    def get(self, clause_id: str) -> Optional[Clause]:
        return self.by_id.get(clause_id)


def _truncate_text(text: str, max_length: int = 800) -> str:
    """Truncate text to a maximum length, breaking at word boundaries."""
    if len(text) <= max_length:
        return text

    truncated = text[:max_length]
    last_space = truncated.rfind(' ')

    if last_space > max_length * 0.8:
        truncated = truncated[:last_space]

    return truncated + "..."


class UCCComparer:
    """Coordinates the Universal Clause Comparer pipeline."""

    def __init__(self, options: Optional[ComparisonOptions] = None) -> None:
        self.options = options or ComparisonOptions()

    def compare(self, file_a: bytes, file_b: bytes) -> UCCComparisonResult:
        timings: Dict[str, float] = {}
        warnings: List[str] = []

        start = time.perf_counter()
        clauses_a = self._parse_with_timing(file_a, "parse_a", timings, warnings)
        clauses_b = self._parse_with_timing(file_b, "parse_b", timings, warnings)

        align_start = time.perf_counter()
        alignment = align_clauses(
            clauses_a,
            clauses_b,
            options=AlignmentOptions(
                embedder=self.options.embedder,
                similarity_threshold=self.options.similarity_threshold,
                max_candidates_per_clause=self.options.max_candidates_per_clause,
            ),
        )
        timings["align"] = (time.perf_counter() - align_start) * 1000
        gc.collect()

        lookup_a = ClauseLookup(clauses_a)
        lookup_b = ClauseLookup(clauses_b)
        matches: List[ClauseMatch] = []
        matched_a: set[str] = set()
        matched_b: set[str] = set()

        diff_start = time.perf_counter()
        for clause_a in clauses_a:
            candidates = alignment.get(clause_a.id, [])
            if not candidates:
                continue

            for index, (b_id, similarity) in enumerate(candidates):
                clause_b = lookup_b.get(b_id)
                if not clause_b:
                    continue

                raw_token_diff = diff_tokens(clause_a, clause_b)
                status = classify_status(similarity, raw_token_diff)
                numeric_delta = compute_numeric_delta(clause_a, clause_b)
                strictness_delta = evaluate_strictness(
                    raw_token_diff.get("removed", []), raw_token_diff.get("added", [])
                )
                token_diff = raw_token_diff if self.options.return_token_diffs else None
                review_required = (
                    clause_a.confidence < 0.8
                    or clause_b.confidence < 0.8
                    or similarity < (self.options.similarity_threshold + 0.05)
                )

                match = ClauseMatch(
                    a_id=clause_a.id,
                    b_id=clause_b.id,
                    similarity=float(similarity),
                    status=status,
                    token_diff=token_diff,
                    numeric_delta=numeric_delta or None,
                    strictness_delta=strictness_delta,
                    review_required=review_required,
                    evidence={
                        "a": {
                            "page_start": clause_a.page_start,
                            "page_end": clause_a.page_end,
                        },
                        "b": {
                            "page_start": clause_b.page_start,
                            "page_end": clause_b.page_end,
                        },
                    },
                )
                match = apply_materiality(match, clause_a, clause_b)
                matches.append(match)

                matched_a.add(clause_a.id)
                matched_b.add(clause_b.id)

                if index == 0:
                    break  # Prefer the strongest match; subsequent candidates trigger review entries later

            if candidates and len(candidates) > 1:
                # Add review entries for secondary candidates
                top_secondary = candidates[1 : self.options.max_candidates_per_clause]
                for b_id, similarity in top_secondary:
                    clause_b = lookup_b.get(b_id)
                    if not clause_b:
                        continue
                    match = ClauseMatch(
                        a_id=clause_a.id,
                        b_id=clause_b.id,
                        similarity=float(similarity),
                        status="modified",
                        token_diff=None,
                        numeric_delta=None,
                        strictness_delta=0,
                        review_required=True,
                        evidence={
                            "a": {
                                "page_start": clause_a.page_start,
                                "page_end": clause_a.page_end,
                            },
                            "b": {
                                "page_start": clause_b.page_start,
                                "page_end": clause_b.page_end,
                            },
                        },
                    )
                    match = apply_materiality(match, clause_a, clause_b)
                    matches.append(match)

        unmatched_a_ids = [clause.id for clause in clauses_a if clause.id not in matched_a]
        unmatched_b_ids = [clause.id for clause in clauses_b if clause.id not in matched_b]

        for clause_id in unmatched_a_ids:
            clause = lookup_a.get(clause_id)
            if not clause:
                continue
            match = ClauseMatch(
                a_id=clause.id,
                b_id=None,
                similarity=None,
                status="removed",
                token_diff=None,
                numeric_delta=None,
                materiality_score=0.0,
                strictness_delta=0,
                review_required=clause.confidence < 0.8,
                evidence={
                    "a": {
                        "page_start": clause.page_start,
                        "page_end": clause.page_end,
                    }
                },
            )
            match = apply_materiality(match, clause, None)
            matches.append(match)

        for clause_id in unmatched_b_ids:
            clause = lookup_b.get(clause_id)
            if not clause:
                continue
            match = ClauseMatch(
                a_id=None,
                b_id=clause.id,
                similarity=None,
                status="added",
                token_diff=None,
                numeric_delta=None,
                materiality_score=0.0,
                strictness_delta=0,
                review_required=clause.confidence < 0.8,
                evidence={
                    "b": {
                        "page_start": clause.page_start,
                        "page_end": clause.page_end,
                    }
                },
            )
            match = apply_materiality(match, None, clause)
            matches.append(match)

        timings["diff"] = (time.perf_counter() - diff_start) * 1000
        timings["total"] = (time.perf_counter() - start) * 1000

        self._attach_clause_texts(matches, lookup_a, lookup_b)

        summary = self._build_summary(matches)

        del alignment, lookup_a, lookup_b, clauses_a, clauses_b
        gc.collect()

        return UCCComparisonResult(
            summary=summary,
            matches=matches,
            unmapped_a=unmatched_a_ids,
            unmapped_b=unmatched_b_ids,
            warnings=warnings,
            timings_ms=timings,
        )

    def _parse_with_timing(
        self,
        pdf_bytes: bytes,
        label: str,
        timings: Dict[str, float],
        warnings: List[str],
    ) -> List[Clause]:
        from pdf_parser import parse_document_to_clauses  # local import to avoid circular dependency

        start = time.perf_counter()
        clauses = parse_document_to_clauses(pdf_bytes)
        timings[label] = (time.perf_counter() - start) * 1000
        low_confidence = [clause for clause in clauses if clause.confidence < 0.8]
        if low_confidence:
            warnings.append(
                f"{label}: {len(low_confidence)} clause(s) below confidence threshold"
            )
        return clauses

    def _attach_clause_texts(
        self, matches: List[ClauseMatch], lookup_a: ClauseLookup, lookup_b: ClauseLookup
    ) -> None:
        """Attach truncated clause text snippets to matches for UI display."""
        for match in matches:
            if match.a_id:
                clause_a = lookup_a.get(match.a_id)
                if clause_a:
                    match.a_text = _truncate_text(clause_a.text)
                    match.a_title = clause_a.title

            if match.b_id:
                clause_b = lookup_b.get(match.b_id)
                if clause_b:
                    match.b_text = _truncate_text(clause_b.text)
                    match.b_title = clause_b.title

    def _build_summary(self, matches: Sequence[ClauseMatch]) -> Dict[str, object]:
        counts = {
            "added": 0,
            "removed": 0,
            "modified": 0,
            "unchanged": 0,
        }
        for match in matches:
            if match.status in counts:
                counts[match.status] += 1
        bullets = summarise_matches(matches)
        return {"counts": counts, "bullets": bullets}
