"""SQLite-backed persistence for job tracking.

Stores job metadata, progress, and status for async comparison tasks.
"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


def _default_db_path() -> Path:
    """Get the default database path for job storage."""
    env_path = os.environ.get("UCC_JOBS_DB_PATH")
    if env_path:
        return Path(env_path)
    root = Path(__file__).resolve().parents[1]
    return root / ".data" / "jobs.db"


def _ensure_parent(path: Path) -> None:
    """Ensure parent directory exists."""
    path.parent.mkdir(parents=True, exist_ok=True)


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Create job tracking tables."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            job_id TEXT PRIMARY KEY,
            doc_id_a TEXT NOT NULL,
            doc_id_b TEXT NOT NULL,
            file_name_a TEXT,
            file_name_b TEXT,
            status TEXT NOT NULL DEFAULT 'PENDING',
            current_segment INTEGER DEFAULT 0,
            current_segment_name TEXT DEFAULT '',
            total_segments INTEGER DEFAULT 11,
            progress_pct REAL DEFAULT 0.0,
            error_message TEXT,
            result_data TEXT,
            celery_task_id TEXT,
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_jobs_status
        ON jobs (status)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_jobs_created
        ON jobs (created_at DESC)
        """
    )


class JobStatus(str, Enum):
    """Job execution status."""
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    RETRYING = "RETRYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# Segment names for progress display
SEGMENT_NAMES = {
    0: "Queued",
    1: "Document A: Layout Analysis",
    2: "Document A: Definitions Extraction",
    3: "Document A: Clause Classification",
    4: "Document A: Clause DNA Extraction",
    5: "Document B: Layout Analysis",
    6: "Document B: Definitions Extraction",
    7: "Document B: Clause Classification",
    8: "Document B: Clause DNA Extraction",
    9: "Semantic Alignment",
    10: "Delta Interpretation",
    11: "Narrative Summarisation",
}


@dataclass
class Job:
    """Job data model."""
    job_id: str
    doc_id_a: str
    doc_id_b: str
    status: JobStatus
    current_segment: int = 0
    current_segment_name: str = ""
    total_segments: int = 11
    progress_pct: float = 0.0
    file_name_a: Optional[str] = None
    file_name_b: Optional[str] = None
    error_message: Optional[str] = None
    result_data: Optional[Dict[str, Any]] = None
    celery_task_id: Optional[str] = None
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "job_id": self.job_id,
            "doc_id_a": self.doc_id_a,
            "doc_id_b": self.doc_id_b,
            "file_name_a": self.file_name_a,
            "file_name_b": self.file_name_b,
            "status": self.status.value if isinstance(self.status, JobStatus) else self.status,
            "current_segment": self.current_segment,
            "current_segment_name": self.current_segment_name or SEGMENT_NAMES.get(self.current_segment, ""),
            "total_segments": self.total_segments,
            "progress_pct": round(self.progress_pct, 1),
            "error_message": self.error_message,
            "celery_task_id": self.celery_task_id,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "updated_at": self.updated_at,
        }


class JobStore:
    """SQLite persistence for job tracking."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or _default_db_path()

    def _connect(self) -> sqlite3.Connection:
        """Get a database connection."""
        _ensure_parent(self.db_path)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        _ensure_schema(conn)
        return conn

    def create(
        self,
        job_id: str,
        doc_id_a: str,
        doc_id_b: str,
        *,
        file_name_a: str | None = None,
        file_name_b: str | None = None,
        celery_task_id: str | None = None,
    ) -> Job:
        """Create a new job record."""
        now = datetime.now(timezone.utc).isoformat()
        
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs (
                    job_id, doc_id_a, doc_id_b, file_name_a, file_name_b,
                    status, celery_task_id, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    doc_id_a,
                    doc_id_b,
                    file_name_a,
                    file_name_b,
                    JobStatus.PENDING.value,
                    celery_task_id,
                    now,
                    now,
                ),
            )

        return Job(
            job_id=job_id,
            doc_id_a=doc_id_a,
            doc_id_b=doc_id_b,
            file_name_a=file_name_a,
            file_name_b=file_name_b,
            status=JobStatus.PENDING,
            celery_task_id=celery_task_id,
            created_at=now,
            updated_at=now,
        )

    def get(self, job_id: str) -> Job | None:
        """Get a job by ID."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()

        if not row:
            return None

        return self._row_to_job(row)

    def update(
        self,
        job_id: str,
        *,
        status: JobStatus | str | None = None,
        current_segment: int | None = None,
        current_segment_name: str | None = None,
        progress_pct: float | None = None,
        error_message: str | None = None,
        result_data: Dict[str, Any] | None = None,
        celery_task_id: str | None = None,
        started_at: str | None = None,
        completed_at: str | None = None,
    ) -> Job | None:
        """Update a job record."""
        now = datetime.now(timezone.utc).isoformat()
        
        updates = ["updated_at = ?"]
        params: List[Any] = [now]

        if status is not None:
            status_val = status.value if isinstance(status, JobStatus) else status
            updates.append("status = ?")
            params.append(status_val)

        if current_segment is not None:
            updates.append("current_segment = ?")
            params.append(current_segment)
            # Auto-calculate progress
            if progress_pct is None:
                progress_pct = (current_segment / 11) * 100

        if current_segment_name is not None:
            updates.append("current_segment_name = ?")
            params.append(current_segment_name)

        if progress_pct is not None:
            updates.append("progress_pct = ?")
            params.append(progress_pct)

        if error_message is not None:
            updates.append("error_message = ?")
            params.append(error_message)

        if result_data is not None:
            updates.append("result_data = ?")
            params.append(json.dumps(result_data))

        if celery_task_id is not None:
            updates.append("celery_task_id = ?")
            params.append(celery_task_id)

        if started_at is not None:
            updates.append("started_at = ?")
            params.append(started_at)

        if completed_at is not None:
            updates.append("completed_at = ?")
            params.append(completed_at)

        params.append(job_id)

        with self._connect() as conn:
            conn.execute(
                f"UPDATE jobs SET {', '.join(updates)} WHERE job_id = ?",
                params,
            )

        return self.get(job_id)

    def list_jobs(
        self,
        *,
        status: JobStatus | str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Job]:
        """List jobs with optional filtering."""
        query = "SELECT * FROM jobs"
        params: List[Any] = []

        if status is not None:
            status_val = status.value if isinstance(status, JobStatus) else status
            query += " WHERE status = ?"
            params.append(status_val)

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()

        return [self._row_to_job(row) for row in rows]

    def delete(self, job_id: str) -> bool:
        """Delete a job record."""
        with self._connect() as conn:
            result = conn.execute(
                "DELETE FROM jobs WHERE job_id = ?",
                (job_id,),
            )
        return result.rowcount > 0

    def get_result(self, job_id: str) -> Dict[str, Any] | None:
        """Get the result data for a completed job."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT result_data FROM jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()

        if not row or not row["result_data"]:
            return None

        return json.loads(row["result_data"])

    def _row_to_job(self, row: sqlite3.Row) -> Job:
        """Convert a database row to a Job object."""
        result_data = None
        if row["result_data"]:
            try:
                result_data = json.loads(row["result_data"])
            except json.JSONDecodeError:
                result_data = None

        return Job(
            job_id=row["job_id"],
            doc_id_a=row["doc_id_a"],
            doc_id_b=row["doc_id_b"],
            file_name_a=row["file_name_a"],
            file_name_b=row["file_name_b"],
            status=JobStatus(row["status"]),
            current_segment=row["current_segment"],
            current_segment_name=row["current_segment_name"] or "",
            total_segments=row["total_segments"],
            progress_pct=row["progress_pct"],
            error_message=row["error_message"],
            result_data=result_data,
            celery_task_id=row["celery_task_id"],
            created_at=row["created_at"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            updated_at=row["updated_at"],
        )
