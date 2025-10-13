"""Utilities for converting PDF bytes into structured text blocks."""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import List, Sequence

import pdfplumber


@dataclass
class Block:
    """Represents a contiguous text block extracted from a PDF page."""

    id: str
    page_number: int
    text: str
    bbox: Sequence[float]
    page_width: float
    page_height: float
    fonts: List[str] = field(default_factory=list)
    section_path: List[str] = field(default_factory=list)
    is_admin: bool = False
    clause_type: str | None = None
    ors: float | None = None
    max_sim_positive: float | None = None
    max_sim_negative: float | None = None
    concepts: List[str] = field(default_factory=list)
    why_kept: List[str] = field(default_factory=list)


def _group_words_into_lines(words: Sequence[dict]) -> List[List[dict]]:
    """Cluster pdfplumber word dictionaries into line-based groups."""

    if not words:
        return []

    lines: List[List[dict]] = []
    current_line: List[dict] = []
    last_top = None
    for word in sorted(words, key=lambda w: (w.get("top", 0.0), w.get("x0", 0.0))):
        top = word.get("top")
        if last_top is None:
            current_line.append(word)
            last_top = top
            continue
        if top is None or last_top is None:
            current_line.append(word)
            continue
        if abs(top - last_top) <= 3.0:
            current_line.append(word)
        else:
            lines.append(current_line)
            current_line = [word]
            last_top = top
    if current_line:
        lines.append(current_line)
    return lines


def _merge_line(line: Sequence[dict]) -> Block:
    text = " ".join(word.get("text", "") for word in line).strip()
    x0 = min(word.get("x0", 0.0) for word in line)
    y0 = min(word.get("top", 0.0) for word in line)
    x1 = max(word.get("x1", 0.0) for word in line)
    y1 = max(word.get("bottom", 0.0) for word in line)
    fonts = sorted({word.get("fontname", "") for word in line if word.get("fontname")})
    page = line[0].get("page_number", 1)
    width = line[0].get("page_width", 0.0)
    height = line[0].get("page_height", 0.0)
    return Block(
        id="",
        page_number=int(page),
        text=text,
        bbox=(x0, y0, x1, y1),
        page_width=width,
        page_height=height,
        fonts=list(fonts),
    )


def _annotate_words(words: Sequence[dict], page_number: int, width: float, height: float) -> None:
    for word in words:
        word["page_number"] = page_number
        word["page_width"] = width
        word["page_height"] = height


def load_pdf_blocks(pdf_bytes: bytes) -> List[Block]:
    """Parse a PDF document into individual text blocks.

    The function favours deterministic behaviour: no caching, no background state.
    """

    if not pdf_bytes:
        return []

    output: List[Block] = []
    buffer = io.BytesIO(pdf_bytes)
    with pdfplumber.open(buffer) as document:
        for page_index, page in enumerate(document.pages, start=1):
            words = page.extract_words(use_text_flow=True, keep_blank_chars=False)
            _annotate_words(words, page_index, page.width or 0.0, page.height or 0.0)
            for line_index, line in enumerate(_group_words_into_lines(words), start=1):
                block = _merge_line(line)
                block.id = f"p{page_index}_b{line_index}"
                output.append(block)
    return output
