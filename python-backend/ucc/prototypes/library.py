"""Prototype-based similarity scoring."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import List, Sequence

import numpy as np
import yaml
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel

_SEEDS_DIR = Path(__file__).resolve().parent.parent / "seeds"


@dataclass
class PrototypeScores:
    max_sim_positive: float
    max_sim_negative: float


class PrototypeLibrary:
    """Holds deterministic TF-IDF representations of prototype snippets."""

    def __init__(self, positive: Sequence[str], negative: Sequence[str]) -> None:
        self.positive = list(positive)
        self.negative = list(negative)
        self.vectorizer = TfidfVectorizer(stop_words="english")
        self._fit()

    def _fit(self) -> None:
        corpus = self.positive + self.negative
        if not corpus:
            self.vectorizer.fit([""])
            self.positive_matrix = self.vectorizer.transform([""])
            self.negative_matrix = self.vectorizer.transform([""])
            return
        matrix = self.vectorizer.fit_transform(corpus)
        pos_count = len(self.positive)
        self.positive_matrix = matrix[:pos_count]
        self.negative_matrix = matrix[pos_count:] if self.negative else self.vectorizer.transform([""])

    def score(self, texts: Sequence[str]) -> List[PrototypeScores]:
        if not texts:
            return []
        embeddings = self.vectorizer.transform(texts)
        pos_scores = linear_kernel(embeddings, self.positive_matrix)
        if self.negative:
            neg_scores = linear_kernel(embeddings, self.negative_matrix)
        else:
            neg_scores = np.zeros((embeddings.shape[0], 1))
        return [
            PrototypeScores(
                max_sim_positive=float(np.max(pos_scores[i])) if pos_scores.size else 0.0,
                max_sim_negative=float(np.max(neg_scores[i])) if neg_scores.size else 0.0,
            )
            for i in range(embeddings.shape[0])
        ]


@lru_cache(maxsize=1)
def load_library() -> PrototypeLibrary:
    pos_path = _SEEDS_DIR / "prototypes_positive.yml"
    neg_path = _SEEDS_DIR / "prototypes_negative.yml"
    if not pos_path.exists() or not neg_path.exists():  # pragma: no cover - defensive
        raise FileNotFoundError("Prototype seed files are missing")
    with pos_path.open("r", encoding="utf-8") as handle:
        positive = yaml.safe_load(handle) or []
    with neg_path.open("r", encoding="utf-8") as handle:
        negative = yaml.safe_load(handle) or []
    return PrototypeLibrary(positive=positive, negative=negative)
