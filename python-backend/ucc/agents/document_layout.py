"""Segment 1: Document Layout Agent."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import List

from ..io.pdf_blocks import Block, load_pdf_blocks
from ..preprocess.furniture import remove_furniture
from ..preprocess.toc import apply_sections
from ..storage.layout_store import LayoutStore, PersistedDocument


@dataclass(frozen=True)
class LayoutResult:
    doc_id: str
    blocks: List[Block]
    source_uri: str | None = None
    persisted: PersistedDocument | None = None


def _stable_block_order(block: Block) -> tuple[int, float, float]:
    x0, y0, _, _ = block.bbox
    return (block.page_number, float(y0), float(x0))


def _hash_for_doc_id(pdf_bytes: bytes) -> str:
    return sha256(pdf_bytes).hexdigest()


def run_document_layout(
    pdf_bytes: bytes,
    *,
    doc_id: str,
    source_uri: str | None = None,
) -> LayoutResult:
    """Parse, clean, sectionise, and persist layout blocks."""

    raw_blocks = load_pdf_blocks(pdf_bytes)
    filtered_blocks = remove_furniture(raw_blocks)
    apply_sections(filtered_blocks)

    ordered_blocks = sorted(filtered_blocks, key=_stable_block_order)

    store = LayoutStore()
    persisted = store.persist(doc_id, source_uri, pdf_bytes, ordered_blocks)

    return LayoutResult(
        doc_id=doc_id,
        blocks=ordered_blocks,
        source_uri=source_uri,
        persisted=persisted,
    )


def get_layout_blocks(doc_id: str) -> List[Block]:
    """Retrieve persisted layout blocks for a document."""

    store = LayoutStore()
    return store.get_blocks(doc_id)


def doc_id_from_pdf(pdf_bytes: bytes) -> str:
    """Stable doc_id helper for callers that only have bytes."""

    return _hash_for_doc_id(pdf_bytes)
