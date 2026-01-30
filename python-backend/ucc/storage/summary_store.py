"""SQLite-backed persistence for narrative summarisation output."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List

from .layout_store import _default_db_path, _ensure_parent


class BulletSeverity(str, Enum):
    """Severity level of a summary bullet."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    REVIEW = "review"


class BulletDirection(str, Enum):
    """Direction of change for a bullet."""

    BROADER = "broader"
    NARROWER = "narrower"
    NEUTRAL = "neutral"
    AMBIGUOUS = "ambiguous"


@dataclass
class EvidenceRef:
    """Reference to evidence supporting a bullet."""

    block_id_a: str
    block_id_b: str | None
    delta_ids: List[str] = field(default_factory=list)
    quote_fragments: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "block_id_a": self.block_id_a,
            "block_id_b": self.block_id_b,
            "delta_ids": self.delta_ids,
            "quote_fragments": self.quote_fragments,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvidenceRef":
        return cls(
            block_id_a=data.get("block_id_a", ""),
            block_id_b=data.get("block_id_b"),
            delta_ids=data.get("delta_ids", []),
            quote_fragments=data.get("quote_fragments", []),
        )


@dataclass
class SummaryBullet:
    """A single summary bullet point."""

    bullet_id: str
    text: str
    severity: BulletSeverity
    delta_types: List[str]
    direction: BulletDirection
    evidence_refs: EvidenceRef
    clause_type: str = ""
    confidence: float = 0.5

    def to_dict(self) -> Dict[str, Any]:
        return {
            "bullet_id": self.bullet_id,
            "text": self.text,
            "severity": self.severity.value,
            "delta_types": self.delta_types,
            "direction": self.direction.value,
            "evidence_refs": self.evidence_refs.to_dict(),
            "clause_type": self.clause_type,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SummaryBullet":
        return cls(
            bullet_id=data.get("bullet_id", ""),
            text=data.get("text", ""),
            severity=BulletSeverity(data.get("severity", "review")),
            delta_types=data.get("delta_types", []),
            direction=BulletDirection(data.get("direction", "ambiguous")),
            evidence_refs=EvidenceRef.from_dict(data.get("evidence_refs", {})),
            clause_type=data.get("clause_type", ""),
            confidence=data.get("confidence", 0.5),
        )


@dataclass
class SummaryCounts:
    """Counts for the comparison summary."""

    matched_clauses: int = 0
    unmatched_clauses: int = 0
    deltas_by_type: Dict[str, int] = field(default_factory=dict)
    review_needed: int = 0
    total_bullets: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "matched_clauses": self.matched_clauses,
            "unmatched_clauses": self.unmatched_clauses,
            "deltas_by_type": self.deltas_by_type,
            "review_needed": self.review_needed,
            "total_bullets": self.total_bullets,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SummaryCounts":
        return cls(
            matched_clauses=data.get("matched_clauses", 0),
            unmatched_clauses=data.get("unmatched_clauses", 0),
            deltas_by_type=data.get("deltas_by_type", {}),
            review_needed=data.get("review_needed", 0),
            total_bullets=data.get("total_bullets", 0),
        )


@dataclass
class NarrativeResult:
    """Output of the narrative summarisation agent."""

    doc_id_a: str
    doc_id_b: str
    bullets: List[SummaryBullet]
    counts: SummaryCounts
    confidence: float = 0.5
    model_info: str | None = None
    generated_at: str = ""


def _ensure_summary_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS comparison_summaries (
            doc_id_a TEXT NOT NULL,
            doc_id_b TEXT NOT NULL,
            summary_bullets TEXT NOT NULL,
            summary_counts TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            model_info TEXT,
            confidence REAL NOT NULL,
            PRIMARY KEY (doc_id_a, doc_id_b)
        )
        """
    )


class SummaryStore:
    """SQLite persistence for narrative summarisation output."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or _default_db_path()

    def _connect(self) -> sqlite3.Connection:
        _ensure_parent(self.db_path)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        _ensure_summary_schema(conn)
        return conn

    def clear_summary(self, doc_id_a: str, doc_id_b: str) -> None:
        """Remove summary for a document pair (idempotent re-run)."""
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM comparison_summaries WHERE doc_id_a = ? AND doc_id_b = ?",
                (doc_id_a, doc_id_b),
            )

    def persist_summary(self, result: NarrativeResult) -> None:
        generated_at = datetime.now(timezone.utc).isoformat()
        bullets_json = json.dumps([b.to_dict() for b in result.bullets])
        counts_json = json.dumps(result.counts.to_dict())

        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO comparison_summaries (
                    doc_id_a, doc_id_b, summary_bullets, summary_counts,
                    generated_at, model_info, confidence
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.doc_id_a,
                    result.doc_id_b,
                    bullets_json,
                    counts_json,
                    generated_at,
                    result.model_info,
                    result.confidence,
                ),
            )

    def get_summary(self, doc_id_a: str, doc_id_b: str) -> NarrativeResult | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM comparison_summaries
                WHERE doc_id_a = ? AND doc_id_b = ?
                """,
                (doc_id_a, doc_id_b),
            ).fetchone()

        if not row:
            return None

        bullets_data = json.loads(row["summary_bullets"])
        counts_data = json.loads(row["summary_counts"])

        return NarrativeResult(
            doc_id_a=row["doc_id_a"],
            doc_id_b=row["doc_id_b"],
            bullets=[SummaryBullet.from_dict(b) for b in bullets_data],
            counts=SummaryCounts.from_dict(counts_data),
            confidence=row["confidence"],
            model_info=row["model_info"],
            generated_at=row["generated_at"],
        )

    def get_bullets(
        self,
        doc_id_a: str,
        doc_id_b: str,
        severity: BulletSeverity | None = None,
    ) -> List[SummaryBullet]:
        result = self.get_summary(doc_id_a, doc_id_b)
        if not result:
            return []

        if severity is None:
            return result.bullets

        return [b for b in result.bullets if b.severity == severity]
