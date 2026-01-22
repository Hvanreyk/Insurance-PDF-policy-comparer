"""SQLite-backed persistence for semantic alignment output."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List

from .layout_store import _default_db_path, _ensure_parent


class AlignmentType(str, Enum):
    """Type of alignment between clauses."""

    ONE_TO_ONE = "one_to_one"
    ONE_TO_MANY = "one_to_many"
    UNMATCHED = "unmatched"


@dataclass
class ClauseAlignment:
    """Alignment between two clauses from different documents."""

    doc_id_a: str
    block_id_a: str
    doc_id_b: str
    block_id_b: str | None  # None if unmatched
    clause_type: str
    alignment_score: float
    score_components: Dict[str, float] = field(default_factory=dict)
    confidence: float = 0.5
    alignment_type: AlignmentType = AlignmentType.ONE_TO_ONE
    notes: str = ""


@dataclass
class AlignmentResult:
    """Output of the semantic alignment agent."""

    doc_id_a: str
    doc_id_b: str
    alignments: List[ClauseAlignment]
    stats: Dict[str, Any] = field(default_factory=dict)


def _ensure_alignment_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS clause_alignments (
            doc_id_a TEXT NOT NULL,
            block_id_a TEXT NOT NULL,
            doc_id_b TEXT NOT NULL,
            block_id_b TEXT,
            clause_type TEXT NOT NULL,
            alignment_score REAL NOT NULL,
            score_components TEXT NOT NULL,
            confidence REAL NOT NULL,
            alignment_type TEXT NOT NULL,
            notes TEXT,
            created_at TEXT NOT NULL,
            PRIMARY KEY (doc_id_a, block_id_a, doc_id_b)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_alignments_docs
        ON clause_alignments (doc_id_a, doc_id_b)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_alignments_block_a
        ON clause_alignments (block_id_a)
        """
    )


class AlignmentStore:
    """SQLite persistence for semantic alignment output."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or _default_db_path()

    def _connect(self) -> sqlite3.Connection:
        _ensure_parent(self.db_path)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        _ensure_alignment_schema(conn)
        return conn

    def clear_alignments(self, doc_id_a: str, doc_id_b: str) -> None:
        """Remove all alignments for a document pair (idempotent re-run)."""
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM clause_alignments WHERE doc_id_a = ? AND doc_id_b = ?",
                (doc_id_a, doc_id_b),
            )

    def persist_alignments(self, alignments: List[ClauseAlignment]) -> None:
        if not alignments:
            return
        created_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            for alignment in alignments:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO clause_alignments (
                        doc_id_a, block_id_a, doc_id_b, block_id_b, clause_type,
                        alignment_score, score_components, confidence,
                        alignment_type, notes, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        alignment.doc_id_a,
                        alignment.block_id_a,
                        alignment.doc_id_b,
                        alignment.block_id_b,
                        alignment.clause_type,
                        alignment.alignment_score,
                        json.dumps(alignment.score_components),
                        alignment.confidence,
                        alignment.alignment_type.value,
                        alignment.notes,
                        created_at,
                    ),
                )

    def get_alignments(self, doc_id_a: str, doc_id_b: str) -> List[ClauseAlignment]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM clause_alignments
                WHERE doc_id_a = ? AND doc_id_b = ?
                ORDER BY clause_type ASC, alignment_score DESC
                """,
                (doc_id_a, doc_id_b),
            ).fetchall()
        return [self._row_to_alignment(row) for row in rows]

    def get_alignment(self, block_id_a: str) -> List[ClauseAlignment]:
        """Get all alignments for a specific block from document A."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM clause_alignments
                WHERE block_id_a = ?
                ORDER BY alignment_score DESC
                """,
                (block_id_a,),
            ).fetchall()
        return [self._row_to_alignment(row) for row in rows]

    def _row_to_alignment(self, row: sqlite3.Row) -> ClauseAlignment:
        return ClauseAlignment(
            doc_id_a=row["doc_id_a"],
            block_id_a=row["block_id_a"],
            doc_id_b=row["doc_id_b"],
            block_id_b=row["block_id_b"],
            clause_type=row["clause_type"],
            alignment_score=row["alignment_score"],
            score_components=json.loads(row["score_components"]),
            confidence=row["confidence"],
            alignment_type=AlignmentType(row["alignment_type"]),
            notes=row["notes"] or "",
        )
