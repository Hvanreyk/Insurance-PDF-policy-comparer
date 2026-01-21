"""SQLite-backed persistence for document layout output."""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Iterable, List

from ..io.pdf_blocks import Block


def _default_db_path() -> Path:
    env_path = os.environ.get("UCC_LAYOUT_DB_PATH")
    if env_path:
        return Path(env_path)
    root = Path(__file__).resolve().parents[1]
    return root / ".data" / "layout.db"


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS documents (
            doc_id TEXT PRIMARY KEY,
            filename TEXT,
            doc_hash TEXT,
            created_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS blocks (
            block_id TEXT PRIMARY KEY,
            doc_id TEXT NOT NULL,
            page_number INTEGER NOT NULL,
            x0 REAL NOT NULL,
            y0 REAL NOT NULL,
            x1 REAL NOT NULL,
            y1 REAL NOT NULL,
            page_width REAL NOT NULL,
            page_height REAL NOT NULL,
            bbox TEXT NOT NULL,
            text TEXT NOT NULL,
            fonts TEXT NOT NULL,
            section_path TEXT NOT NULL,
            is_admin INTEGER NOT NULL,
            FOREIGN KEY(doc_id) REFERENCES documents(doc_id)
        )
        """
    )


def _hash_bytes(payload: bytes) -> str:
    return sha256(payload).hexdigest()


@dataclass(frozen=True)
class PersistedDocument:
    doc_id: str
    filename: str
    doc_hash: str
    created_at: str


class LayoutStore:
    """SQLite persistence for layout output."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or _default_db_path()

    def _connect(self) -> sqlite3.Connection:
        _ensure_parent(self.db_path)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        _ensure_schema(conn)
        return conn

    def persist(
        self,
        doc_id: str,
        filename: str | None,
        pdf_bytes: bytes,
        blocks: Iterable[Block],
    ) -> PersistedDocument:
        doc_hash = _hash_bytes(pdf_bytes)
        created_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO documents (doc_id, filename, doc_hash, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (doc_id, filename or "", doc_hash, created_at),
            )
            conn.execute("DELETE FROM blocks WHERE doc_id = ?", (doc_id,))
            for block in blocks:
                x0, y0, x1, y1 = block.bbox
                conn.execute(
                    """
                    INSERT INTO blocks (
                        block_id, doc_id, page_number, x0, y0, x1, y1,
                        page_width, page_height, bbox, text, fonts, section_path, is_admin
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        block.id,
                        doc_id,
                        block.page_number,
                        float(x0),
                        float(y0),
                        float(x1),
                        float(y1),
                        float(block.page_width),
                        float(block.page_height),
                        json.dumps(list(block.bbox)),
                        block.text,
                        json.dumps(block.fonts),
                        json.dumps(block.section_path),
                        int(block.is_admin),
                    ),
                )
        return PersistedDocument(
            doc_id=doc_id,
            filename=filename or "",
            doc_hash=doc_hash,
            created_at=created_at,
        )

    def get_blocks(self, doc_id: str) -> List[Block]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM blocks
                WHERE doc_id = ?
                ORDER BY page_number ASC, y0 ASC, x0 ASC
                """,
                (doc_id,),
            ).fetchall()
        blocks: List[Block] = []
        for row in rows:
            bbox = json.loads(row["bbox"])
            block = Block(
                id=row["block_id"],
                page_number=row["page_number"],
                text=row["text"],
                bbox=bbox,
                page_width=row["page_width"],
                page_height=row["page_height"],
                fonts=json.loads(row["fonts"]),
            )
            block.section_path = json.loads(row["section_path"])
            block.is_admin = bool(row["is_admin"])
            blocks.append(block)
        return blocks
