"""SQLite-backed persistence for definitions extraction output."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List

from .layout_store import _default_db_path, _ensure_parent


class DefinitionType(str, Enum):
    GLOSSARY = "glossary"
    INLINE = "inline"
    REFERENTIAL = "referential"


@dataclass
class Definition:
    """A single extracted definition."""

    definition_id: str
    doc_id: str
    term_canonical: str
    term_surface: str
    definition_text: str
    source_block_id: str
    source_page: int
    confidence: float
    definition_type: DefinitionType


@dataclass
class TermMention:
    """A mention of a defined term in a block."""

    mention_id: str
    doc_id: str
    block_id: str
    term_canonical: str
    span_start: int
    span_end: int
    context_snippet: str


@dataclass
class BlockExpansion:
    """Expanded text for a block with definitions inlined."""

    doc_id: str
    block_id: str
    expanded_text: str
    expansion_meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DefinitionsResult:
    """Output of the definitions agent."""

    doc_id: str
    definitions: List[Definition]
    mentions: List[TermMention]
    expansions: List[BlockExpansion]


def _ensure_definitions_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS definitions (
            definition_id TEXT PRIMARY KEY,
            doc_id TEXT NOT NULL,
            term_canonical TEXT NOT NULL,
            term_surface TEXT NOT NULL,
            definition_text TEXT NOT NULL,
            source_block_id TEXT NOT NULL,
            source_page INTEGER NOT NULL,
            confidence REAL NOT NULL,
            definition_type TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(doc_id, term_canonical)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_definitions_doc_id
        ON definitions (doc_id)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS term_mentions (
            mention_id TEXT PRIMARY KEY,
            doc_id TEXT NOT NULL,
            block_id TEXT NOT NULL,
            term_canonical TEXT NOT NULL,
            span_start INTEGER NOT NULL,
            span_end INTEGER NOT NULL,
            context_snippet TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_mentions_doc_block
        ON term_mentions (doc_id, block_id)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS block_expansions (
            doc_id TEXT NOT NULL,
            block_id TEXT NOT NULL,
            expanded_text TEXT NOT NULL,
            expansion_meta TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (doc_id, block_id)
        )
        """
    )


class DefinitionsStore:
    """SQLite persistence for definitions extraction output."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or _default_db_path()

    def _connect(self) -> sqlite3.Connection:
        _ensure_parent(self.db_path)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        _ensure_definitions_schema(conn)
        return conn

    def clear_definitions(self, doc_id: str) -> None:
        """Remove all definitions data for a document (idempotent re-run)."""
        with self._connect() as conn:
            conn.execute("DELETE FROM definitions WHERE doc_id = ?", (doc_id,))
            conn.execute("DELETE FROM term_mentions WHERE doc_id = ?", (doc_id,))
            conn.execute("DELETE FROM block_expansions WHERE doc_id = ?", (doc_id,))

    def persist_definitions(self, definitions: List[Definition]) -> None:
        if not definitions:
            return
        created_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            for defn in definitions:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO definitions (
                        definition_id, doc_id, term_canonical, term_surface,
                        definition_text, source_block_id, source_page,
                        confidence, definition_type, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        defn.definition_id,
                        defn.doc_id,
                        defn.term_canonical,
                        defn.term_surface,
                        defn.definition_text,
                        defn.source_block_id,
                        defn.source_page,
                        defn.confidence,
                        defn.definition_type.value,
                        created_at,
                    ),
                )

    def persist_mentions(self, mentions: List[TermMention]) -> None:
        if not mentions:
            return
        created_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            for mention in mentions:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO term_mentions (
                        mention_id, doc_id, block_id, term_canonical,
                        span_start, span_end, context_snippet, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        mention.mention_id,
                        mention.doc_id,
                        mention.block_id,
                        mention.term_canonical,
                        mention.span_start,
                        mention.span_end,
                        mention.context_snippet,
                        created_at,
                    ),
                )

    def persist_expansions(self, expansions: List[BlockExpansion]) -> None:
        if not expansions:
            return
        created_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            for exp in expansions:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO block_expansions (
                        doc_id, block_id, expanded_text, expansion_meta, created_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        exp.doc_id,
                        exp.block_id,
                        exp.expanded_text,
                        json.dumps(exp.expansion_meta),
                        created_at,
                    ),
                )

    def get_definitions(self, doc_id: str) -> List[Definition]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM definitions WHERE doc_id = ?
                ORDER BY term_canonical ASC
                """,
                (doc_id,),
            ).fetchall()
        return [
            Definition(
                definition_id=row["definition_id"],
                doc_id=row["doc_id"],
                term_canonical=row["term_canonical"],
                term_surface=row["term_surface"],
                definition_text=row["definition_text"],
                source_block_id=row["source_block_id"],
                source_page=row["source_page"],
                confidence=row["confidence"],
                definition_type=DefinitionType(row["definition_type"]),
            )
            for row in rows
        ]

    def get_mentions(self, doc_id: str, block_id: str | None = None) -> List[TermMention]:
        with self._connect() as conn:
            if block_id:
                rows = conn.execute(
                    """
                    SELECT * FROM term_mentions
                    WHERE doc_id = ? AND block_id = ?
                    ORDER BY span_start ASC
                    """,
                    (doc_id, block_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM term_mentions
                    WHERE doc_id = ?
                    ORDER BY block_id ASC, span_start ASC
                    """,
                    (doc_id,),
                ).fetchall()
        return [
            TermMention(
                mention_id=row["mention_id"],
                doc_id=row["doc_id"],
                block_id=row["block_id"],
                term_canonical=row["term_canonical"],
                span_start=row["span_start"],
                span_end=row["span_end"],
                context_snippet=row["context_snippet"],
            )
            for row in rows
        ]

    def get_expansion(self, doc_id: str, block_id: str) -> BlockExpansion | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM block_expansions
                WHERE doc_id = ? AND block_id = ?
                """,
                (doc_id, block_id),
            ).fetchone()
        if not row:
            return None
        return BlockExpansion(
            doc_id=row["doc_id"],
            block_id=row["block_id"],
            expanded_text=row["expanded_text"],
            expansion_meta=json.loads(row["expansion_meta"]),
        )

    def get_all_expansions(self, doc_id: str) -> List[BlockExpansion]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM block_expansions
                WHERE doc_id = ?
                ORDER BY block_id ASC
                """,
                (doc_id,),
            ).fetchall()
        return [
            BlockExpansion(
                doc_id=row["doc_id"],
                block_id=row["block_id"],
                expanded_text=row["expanded_text"],
                expansion_meta=json.loads(row["expansion_meta"]),
            )
            for row in rows
        ]
