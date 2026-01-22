"""SQLite-backed persistence for clause classification output."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List

from .layout_store import _default_db_path, _ensure_parent


class ClauseType(str, Enum):
    """Closed set of clause types for classification."""

    COVERAGE_GRANT = "COVERAGE_GRANT"
    EXCLUSION = "EXCLUSION"
    CONDITION = "CONDITION"
    LIMIT = "LIMIT"
    SUBLIMIT = "SUBLIMIT"
    EXTENSION = "EXTENSION"
    ENDORSEMENT = "ENDORSEMENT"
    DEFINITION = "DEFINITION"
    WARRANTY = "WARRANTY"
    ADMIN = "ADMIN"
    UNCERTAIN = "UNCERTAIN"


# Precedence order for conflict resolution (higher index = lower precedence)
CLAUSE_TYPE_PRECEDENCE: List[ClauseType] = [
    ClauseType.ADMIN,
    ClauseType.DEFINITION,
    ClauseType.EXCLUSION,
    ClauseType.CONDITION,
    ClauseType.WARRANTY,
    ClauseType.LIMIT,
    ClauseType.SUBLIMIT,
    ClauseType.EXTENSION,
    ClauseType.ENDORSEMENT,
    ClauseType.COVERAGE_GRANT,
]


@dataclass
class BlockClassification:
    """Classification result for a single block."""

    doc_id: str
    block_id: str
    clause_type: ClauseType
    confidence: float
    signals: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ClassificationResult:
    """Output of the classification agent."""

    doc_id: str
    classifications: List[BlockClassification]
    stats: Dict[str, int] = field(default_factory=dict)


def _ensure_classification_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS block_classifications (
            doc_id TEXT NOT NULL,
            block_id TEXT NOT NULL,
            clause_type TEXT NOT NULL,
            confidence REAL NOT NULL,
            signals TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (doc_id, block_id)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_classifications_doc_type
        ON block_classifications (doc_id, clause_type)
        """
    )


class ClassificationStore:
    """SQLite persistence for clause classification output."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or _default_db_path()

    def _connect(self) -> sqlite3.Connection:
        _ensure_parent(self.db_path)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        _ensure_classification_schema(conn)
        return conn

    def clear_classifications(self, doc_id: str) -> None:
        """Remove all classifications for a document (idempotent re-run)."""
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM block_classifications WHERE doc_id = ?", (doc_id,)
            )

    def persist_classifications(
        self, classifications: List[BlockClassification]
    ) -> None:
        if not classifications:
            return
        created_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            for clf in classifications:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO block_classifications (
                        doc_id, block_id, clause_type, confidence, signals, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        clf.doc_id,
                        clf.block_id,
                        clf.clause_type.value,
                        clf.confidence,
                        json.dumps(clf.signals),
                        created_at,
                    ),
                )

    def get_classification(self, doc_id: str, block_id: str) -> BlockClassification | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM block_classifications
                WHERE doc_id = ? AND block_id = ?
                """,
                (doc_id, block_id),
            ).fetchone()
        if not row:
            return None
        return BlockClassification(
            doc_id=row["doc_id"],
            block_id=row["block_id"],
            clause_type=ClauseType(row["clause_type"]),
            confidence=row["confidence"],
            signals=json.loads(row["signals"]),
        )

    def get_all_classifications(self, doc_id: str) -> List[BlockClassification]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM block_classifications
                WHERE doc_id = ?
                ORDER BY block_id ASC
                """,
                (doc_id,),
            ).fetchall()
        return [
            BlockClassification(
                doc_id=row["doc_id"],
                block_id=row["block_id"],
                clause_type=ClauseType(row["clause_type"]),
                confidence=row["confidence"],
                signals=json.loads(row["signals"]),
            )
            for row in rows
        ]

    def get_blocks_by_clause_type(
        self, doc_id: str, clause_type: ClauseType
    ) -> List[BlockClassification]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM block_classifications
                WHERE doc_id = ? AND clause_type = ?
                ORDER BY block_id ASC
                """,
                (doc_id, clause_type.value),
            ).fetchall()
        return [
            BlockClassification(
                doc_id=row["doc_id"],
                block_id=row["block_id"],
                clause_type=ClauseType(row["clause_type"]),
                confidence=row["confidence"],
                signals=json.loads(row["signals"]),
            )
            for row in rows
        ]
