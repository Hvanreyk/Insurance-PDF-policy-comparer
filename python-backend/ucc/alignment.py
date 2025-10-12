"""Clause embedding and alignment utilities."""

from __future__ import annotations

import os
from dataclasses import dataclass
import math
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Sequence, Tuple

try:  # pragma: no cover - optional dependency
    import numpy as np
except Exception:  # pragma: no cover - numpy optional
    np = None  # type: ignore

try:  # pragma: no cover - optional dependency
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
except Exception:  # pragma: no cover - sklearn optional
    TfidfVectorizer = None  # type: ignore
    cosine_similarity = None  # type: ignore

from ucc.models_ucc import Clause

try:  # pragma: no cover - optional dependency
    from sentence_transformers import SentenceTransformer
except Exception:  # pragma: no cover - fallback to TF-IDF
    SentenceTransformer = None  # type: ignore

try:  # pragma: no cover - optional dependency
    from openai import OpenAI
except Exception:  # pragma: no cover - optional dependency
    OpenAI = None  # type: ignore

DEFAULT_THRESHOLD = 0.72
DEFAULT_MAX_CANDIDATES = 2


def _clause_to_text(clause: Clause) -> str:
    title = clause.title or ""
    return f"{title}\n{clause.text}".strip()


@dataclass
class AlignmentOptions:
    """Configuration for clause alignment."""

    embedder: str = "auto"
    similarity_threshold: float = DEFAULT_THRESHOLD
    max_candidates_per_clause: int = DEFAULT_MAX_CANDIDATES


class ClauseEmbedder:
    """Embeds clauses using the configured backend."""

    def __init__(self, backend: str = "auto", model_name: str = "all-MiniLM-L6-v2") -> None:
        if backend == "auto":
            if os.environ.get("UCC_EMBEDDER"):
                backend = os.environ["UCC_EMBEDDER"].lower()
            elif SentenceTransformer is not None:
                backend = "sentence-transformer"
            else:
                backend = "tfidf"
        self.backend = backend
        self.model_name = model_name
        self._st_model: Optional[SentenceTransformer] = None
        self._vectorizer: Optional[TfidfVectorizer] = None
        self._openai_client: Optional[OpenAI] = None

    def _ensure_sentence_transformer(self) -> None:
        if SentenceTransformer is None:
            return
        if self._st_model is None:
            self._st_model = SentenceTransformer(self.model_name)

    def _ensure_vectorizer(self) -> None:
        if self._vectorizer is None:
            self._vectorizer = TfidfVectorizer(stop_words="english")

    def _ensure_openai(self) -> None:
        if OpenAI is None:
            raise RuntimeError("openai package not available")
        if self._openai_client is None:
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                raise RuntimeError("OPENAI_API_KEY not configured for OpenAI embedder")
            self._openai_client = OpenAI(api_key=api_key)

    def similarity_matrix(
        self, clauses_a: Sequence[Clause], clauses_b: Sequence[Clause]
    ) -> List[List[float]]:
        texts_a = [_clause_to_text(clause) for clause in clauses_a]
        texts_b = [_clause_to_text(clause) for clause in clauses_b]

        if self.backend == "sentence-transformer" and SentenceTransformer is not None:
            self._ensure_sentence_transformer()
            assert self._st_model is not None
            vectors_a = self._st_model.encode(texts_a, convert_to_numpy=True)
            vectors_b = self._st_model.encode(texts_b, convert_to_numpy=True)
            return self._cosine_similarity(vectors_a, vectors_b)

        if self.backend == "openai":
            self._ensure_openai()
            assert self._openai_client is not None
            model_name = os.environ.get("UCC_OPENAI_MODEL", "text-embedding-3-small")
            vectors_a = self._batch_openai_embed(texts_a, model_name)
            vectors_b = self._batch_openai_embed(texts_b, model_name)
            return self._cosine_similarity(vectors_a, vectors_b)

        if TfidfVectorizer is not None and cosine_similarity is not None and np is not None:
            self._ensure_vectorizer()
            assert self._vectorizer is not None
            combined = texts_a + texts_b
            matrix = self._vectorizer.fit_transform(combined).astype("float32")
            vectors_a = matrix[: len(texts_a)]
            vectors_b = matrix[len(texts_a) :]
            similarities = cosine_similarity(vectors_a, vectors_b)
            return similarities.tolist()

        # Final fallback using SequenceMatcher
        similarities: List[List[float]] = []
        for text_a in texts_a:
            row: List[float] = []
            for text_b in texts_b:
                row.append(SequenceMatcher(None, text_a, text_b).ratio())
            similarities.append(row)
        return similarities

    def _cosine_similarity(self, vectors_a, vectors_b) -> List[List[float]]:
        if np is not None and cosine_similarity is not None:
            array_a = np.asarray(vectors_a, dtype="float32")
            array_b = np.asarray(vectors_b, dtype="float32")
            return cosine_similarity(array_a, array_b).tolist()  # type: ignore[arg-type]

        def _safe_norm(vector: Sequence[float]) -> float:
            return math.sqrt(sum(value * value for value in vector)) or 1.0

        matrix: List[List[float]] = []
        for vec_a in vectors_a:
            row: List[float] = []
            norm_a = _safe_norm(vec_a)
            for vec_b in vectors_b:
                norm_b = _safe_norm(vec_b)
                dot = sum(x * y for x, y in zip(vec_a, vec_b))
                row.append(dot / (norm_a * norm_b))
            matrix.append(row)
        return matrix

    def _batch_openai_embed(self, texts: Sequence[str], model_name: str) -> np.ndarray:
        assert self._openai_client is not None
        embeddings: List[List[float]] = []
        for text in texts:
            response = self._openai_client.embeddings.create(model=model_name, input=text)
            embeddings.append(response.data[0].embedding)
        return np.asarray(embeddings, dtype=np.float32)


def _section_similarity(path_a: str, path_b: str) -> float:
    parts_a = [part.strip().lower() for part in path_a.split(">") if part.strip()]
    parts_b = [part.strip().lower() for part in path_b.split(">") if part.strip()]
    if not parts_a or not parts_b:
        return 0.0
    intersection = len(set(parts_a).intersection(parts_b))
    return intersection / max(len(parts_a), len(parts_b))


def align_clauses(
    clauses_a: Sequence[Clause],
    clauses_b: Sequence[Clause],
    *,
    options: Optional[AlignmentOptions] = None,
) -> Dict[str, List[Tuple[str, float]]]:
    """Return candidate alignments for each clause in the first document."""

    if options is None:
        options = AlignmentOptions()

    embedder = ClauseEmbedder(options.embedder)
    alignment: Dict[str, List[Tuple[str, float]]] = {}

    clauses_by_type_a: Dict[str, List[Clause]] = {}
    clauses_by_type_b: Dict[str, List[Clause]] = {}
    for clause in clauses_a:
        clauses_by_type_a.setdefault(clause.type, []).append(clause)
    for clause in clauses_b:
        clauses_by_type_b.setdefault(clause.type, []).append(clause)

    for clause_type, group_a in clauses_by_type_a.items():
        group_b = clauses_by_type_b.get(clause_type)
        if not group_b:
            continue

        similarity_matrix = embedder.similarity_matrix(group_a, group_b)

        for i, clause_a in enumerate(group_a):
            scores: List[Tuple[str, float]] = []
            for j, clause_b in enumerate(group_b):
                section_score = _section_similarity(clause_a.section_path, clause_b.section_path)
                combined_score = 0.85 * similarity_matrix[i][j] + 0.15 * section_score
                if combined_score >= options.similarity_threshold:
                    scores.append((clause_b.id, float(combined_score)))
            scores.sort(key=lambda item: item[1], reverse=True)
            if scores:
                alignment[clause_a.id] = scores[: options.max_candidates_per_clause]

    return alignment
