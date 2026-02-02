"""PDF file storage for Celery task processing.

Stores PDF files on disk so they can be accessed by both API and Celery workers
without passing large byte arrays through the message queue.
"""

from __future__ import annotations

import os
import shutil
from hashlib import sha256
from pathlib import Path
from typing import Optional


# Default storage path - can be overridden via environment variable
DEFAULT_PDF_STORAGE_PATH = "/data/pdfs"


def get_storage_path() -> Path:
    """Get the PDF storage directory path.
    
    Returns:
        Path to the PDF storage directory
    """
    path = Path(os.environ.get("UCC_PDF_STORAGE_PATH", DEFAULT_PDF_STORAGE_PATH))
    path.mkdir(parents=True, exist_ok=True)
    return path


def generate_doc_id(pdf_bytes: bytes) -> str:
    """Generate a stable document ID from PDF bytes.
    
    Args:
        pdf_bytes: Raw PDF file bytes
        
    Returns:
        SHA256 hash of the PDF bytes
    """
    return sha256(pdf_bytes).hexdigest()


def save_pdf(pdf_bytes: bytes, doc_id: Optional[str] = None) -> tuple[str, Path]:
    """Save a PDF file to storage.
    
    Args:
        pdf_bytes: Raw PDF file bytes
        doc_id: Optional pre-generated document ID
        
    Returns:
        Tuple of (doc_id, file_path)
    """
    if doc_id is None:
        doc_id = generate_doc_id(pdf_bytes)
    
    storage_path = get_storage_path()
    file_path = storage_path / f"{doc_id}.pdf"
    
    # Only write if file doesn't exist (deduplication)
    if not file_path.exists():
        # Write to temp file first, then atomic move
        temp_path = storage_path / f".{doc_id}.pdf.tmp"
        try:
            with open(temp_path, "wb") as f:
                f.write(pdf_bytes)
            temp_path.rename(file_path)
        except Exception:
            # Clean up temp file on failure
            if temp_path.exists():
                temp_path.unlink()
            raise
    
    return doc_id, file_path


def load_pdf(doc_id: str) -> bytes:
    """Load a PDF file from storage.
    
    Args:
        doc_id: Document identifier
        
    Returns:
        Raw PDF file bytes
        
    Raises:
        FileNotFoundError: If the PDF file doesn't exist
    """
    storage_path = get_storage_path()
    file_path = storage_path / f"{doc_id}.pdf"
    
    if not file_path.exists():
        raise FileNotFoundError(f"PDF not found for doc_id: {doc_id}")
    
    with open(file_path, "rb") as f:
        return f.read()


def get_pdf_path(doc_id: str) -> Path:
    """Get the path to a stored PDF file.
    
    Args:
        doc_id: Document identifier
        
    Returns:
        Path to the PDF file
        
    Raises:
        FileNotFoundError: If the PDF file doesn't exist
    """
    storage_path = get_storage_path()
    file_path = storage_path / f"{doc_id}.pdf"
    
    if not file_path.exists():
        raise FileNotFoundError(f"PDF not found for doc_id: {doc_id}")
    
    return file_path


def pdf_exists(doc_id: str) -> bool:
    """Check if a PDF file exists in storage.
    
    Args:
        doc_id: Document identifier
        
    Returns:
        True if the PDF exists
    """
    storage_path = get_storage_path()
    file_path = storage_path / f"{doc_id}.pdf"
    return file_path.exists()


def delete_pdf(doc_id: str) -> bool:
    """Delete a PDF file from storage.
    
    Args:
        doc_id: Document identifier
        
    Returns:
        True if deleted, False if didn't exist
    """
    storage_path = get_storage_path()
    file_path = storage_path / f"{doc_id}.pdf"
    
    if file_path.exists():
        file_path.unlink()
        return True
    return False


def cleanup_job_pdfs(doc_id_a: str, doc_id_b: str) -> None:
    """Clean up PDF files for a completed job.
    
    Only deletes files that aren't shared with other jobs.
    
    Args:
        doc_id_a: Document A identifier
        doc_id_b: Document B identifier
    """
    # For now, we keep PDFs for potential re-use
    # In production, you might want reference counting or TTL cleanup
    pass


def get_storage_stats() -> dict:
    """Get storage statistics.
    
    Returns:
        Dict with storage stats (file count, total size, etc.)
    """
    storage_path = get_storage_path()
    
    pdf_files = list(storage_path.glob("*.pdf"))
    total_size = sum(f.stat().st_size for f in pdf_files if f.is_file())
    
    return {
        "storage_path": str(storage_path),
        "file_count": len(pdf_files),
        "total_size_bytes": total_size,
        "total_size_mb": round(total_size / (1024 * 1024), 2),
    }
