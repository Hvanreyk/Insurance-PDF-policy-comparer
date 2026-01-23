"""SQLite-backed persistence for delta interpretation output."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List

from .layout_store import _default_db_path, _ensure_parent


class DeltaType(str, Enum):
    """Type of change detected between aligned clauses."""

    SCOPE_CHANGE = "scope_change"
    STRICTNESS_CHANGE = "strictness_change"
    CARVE_OUT_CHANGE = "carve_out_change"
    BURDEN_SHIFT_CHANGE = "burden_shift_change"
    NUMERIC_CHANGE = "numeric_change"
    DEFINITION_DEPENDENCY_CHANGE = "definition_dependency_change"
    TEMPORAL_CHANGE = "temporal_change"


class DeltaDirection(str, Enum):
    """Direction of the change in coverage/protection."""

    BROADER = "broader"
    NARROWER = "narrower"
    NEUTRAL = "neutral"
    AMBIGUOUS = "ambiguous"


@dataclass
class ClauseDelta:
    """A single detected change between aligned clauses."""

    doc_id_a: str
    block_id_a: str
    doc_id_b: str
    block_id_b: str
    clause_type: str
    delta_type: DeltaType
    direction: DeltaDirection
    details: Dict[str, Any] = field(default_factory=dict)
    evidence: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.5


@dataclass
class DeltaResult:
    """Output of the delta interpretation agent."""

    doc_id_a: str
    doc_id_b: str
    deltas: List[ClauseDelta]
    stats: Dict[str, Any] = field(default_factory=dict)


def _ensure_delta_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS clause_deltas (
            doc_id_a TEXT NOT NULL,
            block_id_a TEXT NOT NULL,
            doc_id_b TEXT NOT NULL,
            block_id_b TEXT NOT NULL,
            clause_type TEXT NOT NULL,
            delta_type TEXT NOT NULL,
            direction TEXT NOT NULL,
            details TEXT NOT NULL,
            evidence TEXT NOT NULL,
            confidence REAL NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (doc_id_a, block_id_a, doc_id_b, block_id_b, delta_type)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_deltas_docs
        ON clause_deltas (doc_id_a, doc_id_b)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_deltas_block_a
        ON clause_deltas (block_id_a)
        """
    )


class DeltaStore:
    """SQLite persistence for delta interpretation output."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or _default_db_path()

    def _connect(self) -> sqlite3.Connection:
        _ensure_parent(self.db_path)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        _ensure_delta_schema(conn)
        return conn

    def clear_deltas(self, doc_id_a: str, doc_id_b: str) -> None:
        """Remove all deltas for a document pair (idempotent re-run)."""
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM clause_deltas WHERE doc_id_a = ? AND doc_id_b = ?",
                (doc_id_a, doc_id_b),
            )

    def persist_deltas(self, deltas: List[ClauseDelta]) -> None:
        if not deltas:
            return
        created_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            for delta in deltas:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO clause_deltas (
                        doc_id_a, block_id_a, doc_id_b, block_id_b, clause_type,
                        delta_type, direction, details, evidence, confidence, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        delta.doc_id_a,
                        delta.block_id_a,
                        delta.doc_id_b,
                        delta.block_id_b,
                        delta.clause_type,
                        delta.delta_type.value,
                        delta.direction.value,
                        json.dumps(delta.details),
                        json.dumps(delta.evidence),
                        delta.confidence,
                        created_at,
                    ),
                )

    def get_deltas(self, doc_id_a: str, doc_id_b: str) -> List[ClauseDelta]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM clause_deltas
                WHERE doc_id_a = ? AND doc_id_b = ?
                ORDER BY clause_type ASC, delta_type ASC
                """,
                (doc_id_a, doc_id_b),
            ).fetchall()
        return [self._row_to_delta(row) for row in rows]

    def get_deltas_for_clause(self, block_id_a: str) -> List[ClauseDelta]:
        """Get all deltas for a specific clause from document A."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM clause_deltas
                WHERE block_id_a = ?
                ORDER BY delta_type ASC
                """,
                (block_id_a,),
            ).fetchall()
        return [self._row_to_delta(row) for row in rows]

    def _row_to_delta(self, row: sqlite3.Row) -> ClauseDelta:
        return ClauseDelta(
            doc_id_a=row["doc_id_a"],
            block_id_a=row["block_id_a"],
            doc_id_b=row["doc_id_b"],
            block_id_b=row["block_id_b"],
            clause_type=row["clause_type"],
            delta_type=DeltaType(row["delta_type"]),
            direction=DeltaDirection(row["direction"]),
            details=json.loads(row["details"]),
            evidence=json.loads(row["evidence"]),
            confidence=row["confidence"],
        )
