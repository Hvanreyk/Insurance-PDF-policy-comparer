"""Clause alignment utilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

try:  # pragma: no cover - optional dependency
    from rank_bm25 import BM25Okapi
except ModuleNotFoundError:  # pragma: no cover - lightweight fallback
    class BM25Okapi:  # type: ignore[override]
        def __init__(self, corpus: Sequence[Sequence[str]]) -> None:
            self.corpus = [list(doc) for doc in corpus]

        def get_scores(self, query_tokens: Sequence[str]) -> np.ndarray:
            query_set = set(query_tokens)
            scores: List[float] = []
            for doc in self.corpus:
                doc_set = set(doc)
                if not query_set or not doc_set:
                    scores.append(0.0)
                    continue
                intersection = len(query_set & doc_set)
                union = len(query_set | doc_set)
                scores.append(intersection / union)
            return np.asarray(scores, dtype=float)

from ..typing.clauses import ClauseType


@dataclass
class Alignment:
    clause_type: str
    block_id_a: str
    block_id_b: str
    bm25_score: float
    tfidf_score: float
    concept_bonus: float
    final_score: float
    rationale: str


def _tokenise(text: str) -> List[str]:
    return [token for token in text.lower().split() if token]


def _build_bm25_index(blocks: Sequence[dict]) -> Tuple[BM25Okapi, List[List[str]]]:
    tokenised = [_tokenise(block["text"]) for block in blocks]
    return BM25Okapi(tokenised), tokenised


def _tfidf_matrix(blocks_a: Sequence[dict], blocks_b: Sequence[dict]) -> Tuple[TfidfVectorizer, np.ndarray, np.ndarray]:
    corpus = [block["text"] for block in blocks_a] + [block["text"] for block in blocks_b]
    vectorizer = TfidfVectorizer(stop_words="english")
    tfidf = vectorizer.fit_transform(corpus)
    a_matrix = tfidf[: len(blocks_a)]
    b_matrix = tfidf[len(blocks_a) :]
    return vectorizer, a_matrix, b_matrix


def align_blocks(
    blocks_a: Sequence[dict],
    blocks_b: Sequence[dict],
    max_candidates: int = 20,
    concept_bonus: float = 0.05,
) -> List[Alignment]:
    """Align blocks deterministically per clause type."""

    if not blocks_a or not blocks_b:
        return []

    alignments: List[Alignment] = []
    blocks_by_type_a: Dict[str, List[dict]] = {}
    blocks_by_type_b: Dict[str, List[dict]] = {}

    for block in blocks_a:
        blocks_by_type_a.setdefault(block.get("clause_type", ClauseType.UNKNOWN.value), []).append(block)
    for block in blocks_b:
        blocks_by_type_b.setdefault(block.get("clause_type", ClauseType.UNKNOWN.value), []).append(block)

    for clause_type, type_blocks_a in blocks_by_type_a.items():
        type_blocks_b = blocks_by_type_b.get(clause_type)
        if not type_blocks_b:
            continue

        bm25, _ = _build_bm25_index(type_blocks_b)
        _, a_matrix, b_matrix = _tfidf_matrix(type_blocks_a, type_blocks_b)

        for idx_a, block_a in enumerate(type_blocks_a):
            query_tokens = _tokenise(block_a["text"])
            scores = bm25.get_scores(query_tokens)
            if not len(scores):
                continue
            candidate_indices = np.argsort(scores)[::-1][:max_candidates]
            if candidate_indices.size == 0:
                continue

            tfidf_scores = cosine_similarity(a_matrix[idx_a], b_matrix[candidate_indices]).flatten()
            for rank, candidate_idx in enumerate(candidate_indices):
                block_b = type_blocks_b[int(candidate_idx)]
                bm25_score = float(scores[int(candidate_idx)])
                tfidf_score = float(tfidf_scores[rank]) if rank < len(tfidf_scores) else 0.0
                shared_concepts = set(block_a.get("concepts", [])) & set(block_b.get("concepts", []))
                bonus = concept_bonus if shared_concepts else 0.0
                final = bm25_score * 0.4 + tfidf_score * 0.6 + bonus
                rationale = " | ".join(
                    part
                    for part in [
                        f"bm25={bm25_score:.2f}",
                        f"tfidf={tfidf_score:.2f}",
                        f"concept_bonus={bonus:.2f}" if bonus else None,
                    ]
                    if part
                )
                alignments.append(
                    Alignment(
                        clause_type=clause_type,
                        block_id_a=block_a["id"],
                        block_id_b=block_b["id"],
                        bm25_score=bm25_score,
                        tfidf_score=tfidf_score,
                        concept_bonus=bonus,
                        final_score=final,
                        rationale=rationale,
                    )
                )
    alignments.sort(key=lambda a: (a.clause_type, -a.final_score))
    return alignments
