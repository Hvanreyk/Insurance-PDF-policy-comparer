"""SQLite-backed persistence for Clause DNA extraction output."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List

from .layout_store import _default_db_path, _ensure_parent
from .classification_store import ClauseType


class Polarity(str, Enum):
    """Effect direction of a clause."""

    GRANT = "grant"
    RESTRICT = "restrict"
    REMOVE = "remove"
    NEUTRAL = "neutral"


class Strictness(str, Enum):
    """How absolute the clause language is."""

    ABSOLUTE = "absolute"
    CONDITIONAL = "conditional"
    DISCRETIONARY = "discretionary"


@dataclass
class ClauseDNA:
    """Structured legal fingerprint for a clause block."""

    doc_id: str
    block_id: str
    clause_type: ClauseType
    polarity: Polarity
    strictness: Strictness
    scope_connectors: List[str] = field(default_factory=list)
    carve_outs: List[str] = field(default_factory=list)
    entities: List[str] = field(default_factory=list)
    numbers: Dict[str, Any] = field(default_factory=dict)
    definition_dependencies: List[str] = field(default_factory=list)
    temporal_constraints: List[str] = field(default_factory=list)
    burden_shift: bool = False
    raw_signals: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.5


@dataclass
class ClauseDNAResult:
    """Output of the Clause DNA agent."""

    doc_id: str
    dna_records: List[ClauseDNA]
    stats: Dict[str, int] = field(default_factory=dict)


def _ensure_dna_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS clause_dna (
            doc_id TEXT NOT NULL,
            block_id TEXT NOT NULL,
            clause_type TEXT NOT NULL,
            polarity TEXT NOT NULL,
            strictness TEXT NOT NULL,
            scope_connectors TEXT NOT NULL,
            carve_outs TEXT NOT NULL,
            entities TEXT NOT NULL,
            numbers TEXT NOT NULL,
            definition_dependencies TEXT NOT NULL,
            temporal_constraints TEXT NOT NULL,
            burden_shift INTEGER NOT NULL,
            raw_signals TEXT NOT NULL,
            confidence REAL NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (doc_id, block_id)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_dna_doc_type
        ON clause_dna (doc_id, clause_type)
        """
    )


class DNAStore:
    """SQLite persistence for Clause DNA output."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or _default_db_path()

    def _connect(self) -> sqlite3.Connection:
        _ensure_parent(self.db_path)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        _ensure_dna_schema(conn)
        return conn

    def clear_dna(self, doc_id: str) -> None:
        """Remove all DNA records for a document (idempotent re-run)."""
        with self._connect() as conn:
            conn.execute("DELETE FROM clause_dna WHERE doc_id = ?", (doc_id,))

    def persist_dna(self, records: List[ClauseDNA]) -> None:
        if not records:
            return
        created_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            for dna in records:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO clause_dna (
                        doc_id, block_id, clause_type, polarity, strictness,
                        scope_connectors, carve_outs, entities, numbers,
                        definition_dependencies, temporal_constraints,
                        burden_shift, raw_signals, confidence, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        dna.doc_id,
                        dna.block_id,
                        dna.clause_type.value,
                        dna.polarity.value,
                        dna.strictness.value,
                        json.dumps(dna.scope_connectors),
                        json.dumps(dna.carve_outs),
                        json.dumps(dna.entities),
                        json.dumps(dna.numbers),
                        json.dumps(dna.definition_dependencies),
                        json.dumps(dna.temporal_constraints),
                        int(dna.burden_shift),
                        json.dumps(dna.raw_signals),
                        dna.confidence,
                        created_at,
                    ),
                )

    def get_dna(self, doc_id: str, block_id: str) -> ClauseDNA | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM clause_dna
                WHERE doc_id = ? AND block_id = ?
                """,
                (doc_id, block_id),
            ).fetchone()
        if not row:
            return None
        return self._row_to_dna(row)

    def get_all_dna(self, doc_id: str) -> List[ClauseDNA]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM clause_dna
                WHERE doc_id = ?
                ORDER BY block_id ASC
                """,
                (doc_id,),
            ).fetchall()
        return [self._row_to_dna(row) for row in rows]

    def get_dna_by_type(self, doc_id: str, clause_type: ClauseType) -> List[ClauseDNA]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM clause_dna
                WHERE doc_id = ? AND clause_type = ?
                ORDER BY block_id ASC
                """,
                (doc_id, clause_type.value),
            ).fetchall()
        return [self._row_to_dna(row) for row in rows]

    def _row_to_dna(self, row: sqlite3.Row) -> ClauseDNA:
        return ClauseDNA(
            doc_id=row["doc_id"],
            block_id=row["block_id"],
            clause_type=ClauseType(row["clause_type"]),
            polarity=Polarity(row["polarity"]),
            strictness=Strictness(row["strictness"]),
            scope_connectors=json.loads(row["scope_connectors"]),
            carve_outs=json.loads(row["carve_outs"]),
            entities=json.loads(row["entities"]),
            numbers=json.loads(row["numbers"]),
            definition_dependencies=json.loads(row["definition_dependencies"]),
            temporal_constraints=json.loads(row["temporal_constraints"]),
            burden_shift=bool(row["burden_shift"]),
            raw_signals=json.loads(row["raw_signals"]),
            confidence=row["confidence"],
        )
